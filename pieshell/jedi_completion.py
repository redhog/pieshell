import os
import sys
import jedi


def setup_readline(scopes, **kw):
    class JediRL:
        def complete(self, text, state):
            if state == 0:
                sys.path.insert(0, os.getcwd())
                # Calling python doesn't have a path, so add to sys.path.
                try:
                    interpreter = jedi.Interpreter(text, scopes)
                    completions = interpreter.complete(**kw)
                    self.matches = [
                        text[:len(text) - c._like_name_length] + c.name_with_symbols
                        for c in completions
                    ]
                finally:
                    sys.path.pop(0)
            try:
                return self.matches[state]
            except IndexError:
                return None

    import rlcompleter
    import readline
    readline.set_completer(JediRL().complete)
    readline.parse_and_bind("tab: complete")
    readline.parse_and_bind("set completion-ignore-case on")
    readline.parse_and_bind("set show-all-if-unmodified")
    readline.parse_and_bind("set show-all-if-ambiguous on")
    readline.parse_and_bind("set completion-prefix-display-length 2")
    readline.set_completer_delims('')
