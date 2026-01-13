{
  buildPythonApplication,
  setuptools,
  systemd-python
}:

buildPythonApplication {
  pname = "gcroot-relay-server";
  version = "0.1";
  pyproject = true;

  src = ./src;

  build-system = [ setuptools ];

  dependencies = [
    systemd-python
  ];
}
