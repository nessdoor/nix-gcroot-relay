{
  description = "A client/server app for relaying Nix GC root information through vsocks";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
        {
          devShells.default =
	    import ./shell.nix { inherit pkgs; };

          packages = {
	    client = pkgs.python3Packages.callPackage ./client/package.nix { };
	    server = pkgs.python3Packages.callPackage ./server/package.nix { };
          };
        }
    );
}
