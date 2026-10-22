{ pkgs }:
final: prev:
let
  inherit (pkgs) lib;
  # PyTorch needs cuDNN 9, while ONNX Runtime 1.18 needs cuDNN 8.
  # They cannot share a Python distribution, but their SONAMEs can coexist.
  cudnn8 = pkgs.stdenvNoCC.mkDerivation {
    pname = "rvc-onnx-cudnn";
    version = "8.9.6.50";
    src = pkgs.fetchurl {
      url = "https://files.pythonhosted.org/packages/85/2d/3f083fcff1c302119f48e7b30a5f7b23db793f262f900943a9eb456b9e4d/nvidia_cudnn_cu11-8.9.6.50-py3-none-manylinux1_x86_64.whl";
      hash = "sha256-MZqPfKPWUTnxtpmYWVxwdq4OQnGjJeXf3lCjyjH1VYQ=";
    };
    nativeBuildInputs = [
      pkgs.unzip
      pkgs.autoPatchelfHook
    ];
    buildInputs = [
      pkgs.stdenv.cc.cc.lib
      pkgs.zlib
    ];
    autoPatchelfIgnoreMissingDeps = [ "libcuda.so.1" ];
    preFixup = ''
      addAutoPatchelfSearchPath ${final.nvidia-cublas-cu11}/${final.python.sitePackages}/nvidia
      addAutoPatchelfSearchPath ${final.nvidia-cuda-nvrtc-cu11}/${final.python.sitePackages}/nvidia
    '';
    postFixup = ''
      for library in $out/lib/*.so*; do
        patchelf --add-rpath "$out/lib:${final.nvidia-cublas-cu11}/${final.python.sitePackages}/nvidia/cublas/lib:${final.nvidia-cuda-nvrtc-cu11}/${final.python.sitePackages}/nvidia/cuda_nvrtc/lib" "$library"
      done
    '';
    unpackPhase = ''unzip -q "$src"'';
    installPhase = "mkdir -p $out/lib; cp -a nvidia/cudnn/lib/*.so* $out/lib/";
    dontStrip = true;
  };
  cudaNames = builtins.filter (name: lib.hasPrefix "nvidia-" name) (builtins.attrNames prev);
  cudaLibraries = map (name: final.${name}) cudaNames;
  native =
    name: package:
    package.overrideAttrs (old: {
      nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ pkgs.autoPatchelfHook ];
      buildInputs = (old.buildInputs or [ ]) ++ [
        pkgs.stdenv.cc.cc.lib
        pkgs.zlib
      ];
      dontStrip = true;
      autoPatchelfIgnoreMissingDeps = [ "libcuda.so.1" ];
      preFixup =
        (old.preFixup or "")
        + lib.optionalString (name == "torch" || name == "torchaudio" || name == "onnxruntime-gpu") ''
          ${lib.concatMapStringsSep "\n" (
            p: "addAutoPatchelfSearchPath ${p}/${final.python.sitePackages}/nvidia"
          ) cudaLibraries}
        ''
        + lib.optionalString (name == "nvidia-cudnn-cu11" || name == "nvidia-cusolver-cu11") ''
          addAutoPatchelfSearchPath ${final.nvidia-cublas-cu11}/${final.python.sitePackages}/nvidia
          addAutoPatchelfSearchPath ${final.nvidia-cusparse-cu11}/${final.python.sitePackages}/nvidia
        '';
    });
in
(lib.genAttrs cudaNames (name: native name prev.${name}))
// {
  websockets = prev.websockets.overrideAttrs (old: {
    nativeBuildInputs =
      (old.nativeBuildInputs or [ ])
      ++ final.resolveBuildSystem {
        setuptools = [ ];
        wheel = [ ];
      };
  });
  numba = prev.numba.overrideAttrs (old: {
    buildInputs = (old.buildInputs or [ ]) ++ [ pkgs.tbb ];
  });
  torch = native "torch" prev.torch;
  torchaudio = (native "torchaudio" prev.torchaudio).overrideAttrs (old: {
    buildInputs = old.buildInputs ++ [
      final.torch
      pkgs.sox
    ];
    preFixup = old.preFixup + ''
      addAutoPatchelfSearchPath ${final.torch}/${final.python.sitePackages}/torch/lib
    '';
    # Optional FFmpeg 4/5/6 integrations are not used; the CLI handles decoding.
    postInstall = (old.postInstall or "") + ''
      rm -f $out/${final.python.sitePackages}/torio/lib/*ffmpeg*
    '';
  });
  onnxruntime-gpu = (native "onnxruntime-gpu" prev.onnxruntime-gpu).overrideAttrs (old: {
    buildInputs = old.buildInputs ++ [ cudnn8 ];
    # RVC uses the CUDA provider, not the optional TensorRT provider.
    postInstall = (old.postInstall or "") + ''
      rm $out/${final.python.sitePackages}/onnxruntime/capi/libonnxruntime_providers_tensorrt.so
    '';
  });
  sounddevice = prev.sounddevice.overrideAttrs (old: {
    postInstall = (old.postInstall or "") + ''
      substituteInPlace $out/${final.python.sitePackages}/sounddevice.py \
        --replace-fail "_find_library(_libname)" "'${lib.getLib pkgs.portaudio}/lib/libportaudio.so.2'"
    '';
  });
}
