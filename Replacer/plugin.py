###
# Copyright (c) 2015, Michael Daniel Telatynski <postmaster@webdevguru.co.uk>
# Copyright (c) 2015, James Lu <glolol@overdrivenetworks.com>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

###

from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircmsgs as ircmsgs
import supybot.callbacks as callbacks
import supybot.ircutils as ircutils
import supybot.ircdb as ircdb

import re

try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('Replacer')
except ImportError:
    _ = lambda x: x


SED_REGEX = re.compile(r"^(?:(?P<nick>.+?)[:,] )?s(?P<delim>/)(?P<pattern>.*?)(?P=delim)"
                       r"(?P<replacement>.*?)(?:(?P=delim)(?P<flags>[gi]*))?$")

class Replacer(callbacks.PluginRegexp):
    """History replacer using sed regex syntax."""
    threaded = True
    public = True
    unaddressedRegexps = ['replacer']

    @staticmethod
    def _unpack_sed(expr):
        if '\0' in expr:
            raise ValueError('Expression can\'t contain NUL')

        delim = expr[1]
        escaped_expr = ''

        for (i, c) in enumerate(expr):
            if c == delim and i > 0:
                if expr[i - 1] == '\\':
                    escaped_expr = escaped_expr[:-1] + '\0'
                    continue

            escaped_expr += c

        match = SED_REGEX.search(escaped_expr)

        if not match:
            return

        groups = match.groupdict()
        pattern = groups['pattern'].replace('\0', delim)
        replacement = groups['replacement'].replace('\0', delim)

        if groups['flags']:
            raw_flags = set(groups['flags'])
        else:
            raw_flags = set()

        flags = 0
        count = 1

        for flag in raw_flags:
            if flag == 'g':
                count = 0
            if flag == 'i':
                flags |= re.IGNORECASE

        pattern = re.compile(pattern, flags)

        return (pattern, replacement, count)

    def replacer(self, irc, msg, regex):
        if not self.registryValue('enable', msg.args[0]):
            return
        iterable = reversed(irc.state.history)
        msg.tag('Replacer')

        try:
            (pattern, replacement, count) = self._unpack_sed(msg.args[1])
        except (ValueError, re.error) as e:
            self.log.warning(_("Replacer error: %s"), e)
            if self.registryValue('displayErrors', msg.args[0]):
                irc.error(_("Replacer error: %s" % e), Raise=True)
            return

        next(iterable)
        for m in iterable:
            if m.command in ('PRIVMSG', 'NOTICE') and \
                    m.args[0] == msg.args[0]:
                target = regex.group('nick')
                if not ircutils.isNick(str(target), strictRfc=True):
                    return
                if target and m.nick != target:
                    continue
                # Don't snarf ignored users' messages unless specifically
                # told to.
                if ircdb.checkIgnored(m.prefix) and not target:
                    continue
                # When running substitutions, ignore the "* nick" part of any actions.
                action = ircmsgs.isAction(m)
                if action:
                    text = ircmsgs.unAction(m)
                else:
                    text = m.args[1]

                if self.registryValue('ignoreRegex', msg.args[0]) and \
                        m.tagged('Replacer'):
                    continue
                if m.nick == msg.nick:
                    messageprefix = msg.nick
                else:
                    messageprefix = '%s thinks %s' % (msg.nick, m.nick)
                if regexp_wrapper(text, pattern, timeout=0.05, plugin_name=self.name(),
                                  fcn_name='replacer'):
                    if self.registryValue('boldReplacementText', msg.args[0]):
                        replacement = ircutils.bold(replacement)
                    subst = process(pattern.sub, replacement,
                                text, count, timeout=0.05)
                    if action:  # If the message was an ACTION, prepend the nick back.
                        subst = '* %s %s' % (m.nick, subst)
                    irc.reply(_("%s meant to say: %s") %
                              (messageprefix, subst), prefixNick=False)
                    return

        self.log.debug(_("Replacer: Search %r not found in the last %i messages of %s."),
                         msg.args[1], len(irc.state.history), msg.args[0])
        if self.registryValue("displayErrors", msg.args[0]):
            irc.error(_("Search not found in the last %i messages.") %
                      len(irc.state.history), Raise=True)
    replacer.__doc__ = SED_REGEX.pattern

Class = Replacer


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79: