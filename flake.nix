{
  description = "exfat-raw: Raw block-level read/write of exFAT filesystem timestamps";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ self.overlays.default ];
        };
      in
      {
        packages.default = pkgs.exfat-raw;
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [ python3 exfat-raw ];
        };
      }
    )
    // {
      overlays.default = final: prev: {
        exfat-raw = final.python3.pkgs.callPackage ./nix/exfat-raw {
          src = final.lib.cleanSource ./.;
        };
      };
    };
}
