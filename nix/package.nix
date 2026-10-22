{
  lib,
  stdenvNoCC,
  makeWrapper,
  ffmpeg,
  libsndfile,
  environment,
  python,
}:
let
  site = "${environment}/${python.sitePackages}";
  # CUDA/cuDNN and ONNX also load libraries with dlopen, outside ELF NEEDED.
  runtimeLibraries = lib.concatStringsSep ":" (
    [
      "${site}/torch/lib"
      "${site}/onnxruntime/capi"
    ]
    ++ map (name: "${site}/nvidia/${name}/lib") [
      "cublas"
      "cuda_cupti"
      "cuda_nvrtc"
      "cuda_runtime"
      "cudnn"
      "cufft"
      "curand"
      "cusolver"
      "cusparse"
      "nccl"
      "nvtx"
    ]
  );
in
stdenvNoCC.mkDerivation {
  pname = "rvc-webui";
  version = "0.1.0";
  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.union (lib.fileset.intersection
      (lib.fileset.fileFilter (
        file:
        file.name == "LICENSE"
        || builtins.any file.hasExt [
          "py"
          "json"
          "yaml"
          "html"
          "css"
          "js"
        ]
      ) ../.)
      (
        lib.fileset.unions [
          ../webui.py
          ../realtime_gui.py
          ../configs
          ../i18n
          ../infer
          ../tools
          ../train
          ../assets/pymss_weights
          ../LICENSE
          ./launcher.py
          ./download_models.py
          ./doctor.py
        ]
      )
    ) (lib.fileset.fileFilter (file: file.hasExt "md") ../docs);
  };
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  passthru = { inherit runtimeLibraries; };
  installPhase = ''
    runHook preInstall
    mkdir -p $out/share/rvc $out/bin
    cp -r . $out/share/rvc/
    for entry in webui realtime download-models doctor; do
      makeWrapper ${environment}/bin/python $out/bin/rvc-$entry \
        --add-flags "$out/share/rvc/nix/launcher.py $entry" \
        --prefix PATH : ${
          lib.makeBinPath [
            ffmpeg
            environment
          ]
        } \
        --prefix LD_LIBRARY_PATH : ${lib.makeLibraryPath [ libsndfile ]} \
        --prefix LD_LIBRARY_PATH : ${runtimeLibraries} \
        --set PYTHONPATH ${python.pkgs.tkinter}/${python.sitePackages} \
        --set PYTHONNOUSERSITE 1 \
        --set PYTHONDONTWRITEBYTECODE 1
    done
    runHook postInstall
  '';
  meta = {
    description = "Retrieval-based voice conversion with CUDA 11.8";
    license = lib.licenses.mit;
    platforms = [ "x86_64-linux" ];
    mainProgram = "rvc-webui";
  };
}
