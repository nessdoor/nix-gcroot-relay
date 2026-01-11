{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [
    pkgs.bashInteractive
  ];

  packages = with pkgs; [
    (python3.withPackages (pps: with pps; [
      python-lsp-server
      python-lsp-server.passthru.optional-dependencies.all
    ]))
  ];
}
