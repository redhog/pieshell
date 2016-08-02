import jedi.api

def jedi_init(self, source, namespaces, **kwds):
    super(jedi.api.Interpreter, self).__init__(source, **kwds)
    self.namespaces = namespaces

    self._parser = jedi.api.UserContextParser(self._grammar, self.source,
                                              self._orig_path, self._pos,
                                              self._user_context, self._parsed_callback,
                                              use_fast_parser=False)
    jedi.api.interpreter.add_namespaces_to_parser(self._evaluator, namespaces,
                                                  self._parser.module())

jedi.api.Interpreter.__init__ = jedi_init
