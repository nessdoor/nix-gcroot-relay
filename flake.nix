{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";

  outputs = { nixpkgs, ... }:
  {
    devShells.x86_64-linux.default =
      let
	pkgs = import nixpkgs { system = "x86_64-linux"; };
      in
	import ./shell.nix { inherit pkgs; };
  };
}
