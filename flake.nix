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
        apps.test = {
          type = "app";
          program = pkgs.writeShellScript "exfat-raw-test" ''
            export PYTHONPATH="${pkgs.exfat-raw}/${pkgs.exfat-raw.pythonModule.sitePackages}:$PYTHONPATH"
            exec python -m unittest discover -s "${self}/tests" -p 'test_*.py' -v "$@"
          '';
        };
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
