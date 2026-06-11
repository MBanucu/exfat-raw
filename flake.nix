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

        apps.coverage-html = {
          type = "app";
          program = "${pkgs.writeShellApplication {
            name = "coverage-html";
            runtimeInputs = [ pkgs.python3 pkgs.python3Packages.coverage ];
            text = ''
              coverage run -m unittest discover -s tests -p 'test_exfat_raw_image.py' -v
              coverage html -d htmlcov
              echo ""
              echo "Coverage report: file://$(pwd)/htmlcov/index.html"
            '';
          }}/bin/coverage-html";
        };

        devShells.default = pkgs.mkShell {
          inputsFrom = [ pkgs.exfat-raw ];
          packages = with pkgs; [ python3 python3Packages.coverage ];
          shellHook = ''
            echo "exfat-raw dev shell. Run tests:"
            echo "  python -m unittest discover -s tests -p 'test_exfat_raw_image.py' -v   # sandbox-safe (no sudo)"
            echo "  python -m unittest discover -s tests -p 'test_*.py' -v                  # full suite (needs sudo)"
            echo ""
            echo "Coverage:"
            echo "  coverage run -m unittest discover -s tests -p 'test_exfat_raw_image.py' -v"
            echo "  coverage html -d htmlcov"
            echo "  nix run .#coverage-html                                                 # same via flake app"
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
        };
      };
    };
}
