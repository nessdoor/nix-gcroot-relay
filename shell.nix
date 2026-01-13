{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [
    pkgs.bashInteractive
  ];

  packages = with pkgs; [
    nil
    (python3.withPackages (pps: with pps; [
      systemd-python
      python-lsp-server
      python-lsp-server.passthru.optional-dependencies.all
    ]))
    socat
  ];
}
