{
  description = "RVC WebUI and realtime GUI (Python 3.12, CUDA 11.8)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      nixpkgs,
      pyproject-nix,
      uv2nix,
      pyproject-build-systems,
      ...
    }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        config.allowUnfree = true;
      };
      inherit (pkgs) lib;
      python = pkgs.python312;
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
      pythonSet = (pkgs.callPackage pyproject-nix.build.packages { inherit python; }).overrideScope (
        lib.composeManyExtensions [
          pyproject-build-systems.overlays.wheel
          (workspace.mkPyprojectOverlay { sourcePreference = "wheel"; })
          (import ./nix/python-overrides.nix { inherit pkgs; })
        ]
      );
      environment = pythonSet.mkVirtualEnv "rvc-python-env" workspace.deps.default;
      app = pkgs.callPackage ./nix/package.nix { inherit environment python; };
      mkApp = name: {
        type = "app";
        program = "${app}/bin/rvc-${name}";
        meta.description = "RVC ${name}";
      };
    in
    {
      packages.${system} = {
        default = app;
        rvc = app;
        python-env = environment;
      };
      apps.${system} = {
        default = mkApp "webui";
        webui = mkApp "webui";
        realtime = mkApp "realtime";
        download-models = mkApp "download-models";
        doctor = mkApp "doctor";
      };
      devShells.${system}.default = pkgs.mkShell {
        packages = [
          app
          environment
          pkgs.uv
          pkgs.nixfmt
          pkgs.ffmpeg
        ];
        UV_PYTHON = python.interpreter;
        UV_PYTHON_DOWNLOADS = "never";
        UV_NO_SYNC = "1";
        UV_PROJECT_ENVIRONMENT = "${environment}";
        shellHook = ''
          export PYTHONPATH=${python.pkgs.tkinter}/${python.sitePackages}
          export LD_LIBRARY_PATH="''${RVC_DRIVER_LIBRARY_PATH:-/run/opengl-driver/lib}:${app.runtimeLibraries}:${
            lib.makeLibraryPath [ pkgs.libsndfile ]
          }''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
          echo 'RVC: rvc-webui / rvc-realtime / rvc-download-models / rvc-doctor'
        '';
      };
      checks.${system}.runtime = pkgs.runCommand "rvc-runtime-check" { } ''
        export HOME=$TMPDIR/home
        export XDG_DATA_HOME=""
        mkdir -p "$HOME"
        ${app}/bin/rvc-doctor --no-cuda
        test -d "$HOME/.local/share/rvc/assets"
        touch $out
      '';
      formatter.${system} = pkgs.nixfmt;
    };
}
