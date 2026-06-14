{
  description = "exfat-raw: Raw block-level read/write of exFAT filesystem timestamps";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    mount-resolve.url = "github:MBanucu/mount-resolve";
    rawblock-io.url = "github:MBanucu/rawblock-io";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      mount-resolve,
      rawblock-io,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ mount-resolve.overlays.default rawblock-io.overlays.default self.overlays.default ];
        };
      in
      {
        packages.default = pkgs.exfat-raw;

        devShells.default = pkgs.mkShell {
          inputsFrom = [ pkgs.exfat-raw ];
          packages = [ pkgs.python3 ];
          shellHook = ''
            echo "exfat-raw dev shell. Run tests:"
            echo "  python -m unittest discover -s tests -p 'test_exfat_raw_image.py' -v   # sandbox-safe (no sudo)"
            echo "  python -m unittest discover -s tests -p 'test_*.py' -v                  # full suite (needs sudo)"
          '';
        };
      }
    )
    // {
      lib.sitePackages = system:
        let pkg = self.packages.${system}.default;
        in "${pkg}/${pkg.pythonModule.sitePackages}";

      overlays.default = final: prev: {
        exfat-raw = final.python3.pkgs.callPackage ./nix/exfat-raw {
          src = final.lib.cleanSource ./.;
          inherit (final) mount-resolve rawblock-io;
        };
      };
    };
}
