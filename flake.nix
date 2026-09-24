{
  description = "Chore Stars — household participation board";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = {
    self,
    nixpkgs,
  }: let
    systems = ["x86_64-linux" "aarch64-linux"];
    forAllSystems = f:
      nixpkgs.lib.genAttrs systems (system:
        f {
          inherit system;
          pkgs = nixpkgs.legacyPackages.${system};
        });
  in {
    packages = forAllSystems ({pkgs, ...}: rec {
      chore-stars = pkgs.callPackage ./nix/package.nix {};
      default = chore-stars;
    });

    checks = forAllSystems ({system, ...}: {
      chore-stars = self.packages.${system}.default;
    });

    devShells = forAllSystems ({
      pkgs,
      system,
    }: {
      default = pkgs.mkShell {
        inputsFrom = [self.packages.${system}.default];
        packages = [
          pkgs.postgresql
        ];
        env.CHORES_DEV_AUTH = "1";
      };
    });

    nixosModules.default = import ./nix/module.nix {inherit self;};
  };
}
