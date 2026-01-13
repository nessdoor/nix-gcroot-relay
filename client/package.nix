{
  buildPythonApplication,
  setuptools
}:

buildPythonApplication {
  pname = "gcroot-relay-client";
  version = "0.1";
  pyproject = true;

  src = ./src;

  build-system = [ setuptools ];
}
