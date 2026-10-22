# Nixでのインストールと実行

対象は **x86_64 Linux・Python 3.12・CUDA 11.8** です。WebUI（推論・学習）とリアルタイムGUIを同じ環境で提供します。
GTX 1080などのPascal世代に対応するPyTorch `2.7.1+cu118` を使います。

Python依存はuvの `pyproject.toml` / `uv.lock`、システム依存はNixの `flake.nix` / `flake.lock` で管理します。
uv2nixでロックをNixのビルドに取り込み、起動時のpipインストールやインターネット接続は不要です。
モデルのダウンロード時にはインターネット接続が必要です。

## 準備

- Nixの `nix-command` と `flakes` を有効にしてください。
- ホスト側でNVIDIAドライバーを導入してください。カーネルドライバー自体はこのflakeでは変更しません。
- 初回ビルドはCUDA関連の大きなwheelを取得・展開します。モデル用とは別に十分な空き容量が必要です。
- CUDAの非自由ソフトウェアは、このflake内のNixpkgs設定で許可しています。

NixOSでは通常、ドライバーのライブラリは `/run/opengl-driver/lib` に配置されます。
他のLinuxで配置が異なる場合は `RVC_DRIVER_LIBRARY_PATH` に `libcuda.so.1` があるディレクトリを指定してください。
ホストのドライバーライブラリはNix製のランタイムからロードできる必要があります。

## ビルド・起動

リポジトリのルートで実行します。

```bash
nix build

# インポート・音声I/O・FFprobe・CUDA演算・cuDNN・ONNX CUDAライブラリの確認
nix run .#doctor

# WebUI（既定ポート7865）
nix run .#webui -- --noautoopen

# リアルタイムGUI（X11またはXWaylandのDISPLAYが必要）
nix run .#realtime
```

`nix build` の成果物は `result/bin/` にあります。カレントディレクトリに依存せず起動できます。

```bash
./result/bin/rvc-webui --noautoopen --port 7865
./result/bin/rvc-realtime
./result/bin/rvc-doctor --gui
```

継続的に使う場合はユーザープロファイルにインストールできます。

```bash
nix profile add .
rvc-webui --noautoopen
rvc-realtime
```

WebUIは既存実装どおり `0.0.0.0` で待ち受けます。

## モデルとデータ

実行時データの既定ディレクトリは `${XDG_DATA_HOME:-$HOME/.local/share}/rvc` です。
別の場所を使う場合は、モデル取得時とアプリ起動時の両方で同じ `RVC_DATA_DIR` を設定します。

```bash
export RVC_DATA_DIR="$HOME/rvc-data"

# 推論・特徴抽出に必要なHuBERTとRMVPE
nix run .#download-models

# 追加で学習用pretrainedモデルとmuteサンプルを取得
nix run .#download-models -- --training

# 追加でpymss音源分離用モデルを取得
nix run .#download-models -- --separation

# モデルの取得元を固定する場合はHugging FaceのコミットSHAを指定
nix run .#download-models -- --revision <commit-sha>
```

プロファイルにインストールした場合は `rvc-download-models` でも同じ操作ができます。
デフォルトのリビジョンは `main` です。モデルはNixのロック対象に含めません。

```text
$RVC_DATA_DIR/
├── assets/
│   ├── hubert_base/
│   ├── rmvpe/rmvpe.pt
│   ├── pretrained/
│   ├── pretrained_v2/
│   ├── pymss_weights/
│   ├── weights/          # 利用者のRVC .pthモデル
│   └── indices/          # 利用者の.indexファイル
├── logs/                # 学習ログ、生成されたindex、muteサンプル
├── settings/realtime.json
└── .cache/
```

利用者の音声変換モデル `.pth` と `.index` は別途用意してください。
既存環境から移行する場合は、上記のデータを対応するディレクトリへコピーします。
既存のGUI設定は `configs/config.json` から `settings/realtime.json` へコピーできます。

実行ディレクトリのコード用シンボリックリンクは起動時に現在のNixパッケージへ更新されます。
コードのある既存チェックアウト自体を `RVC_DATA_DIR` に指定せず、専用のデータディレクトリを使ってください。
モデル・ログ・GUI設定はパッケージ更新後も保持されます。

## 開発・依存更新

```bash
nix develop

# Nixで構築したPython環境を利用
uv run --no-sync python -c 'import torch; print(torch.__version__, torch.cuda.is_available())'

# Python依存宣言を編集した後、ロックを更新
uv lock

# 依存の更新を明示的に行う場合
uv lock --upgrade

# Nix側の入力を更新
nix flake update

# 再ビルドと検証
nix build
nix flake check
nix run .#doctor
```

開発シェルのPython環境はNix管理の読み取り専用環境です。`uv sync` やpipで変更せず、
`uv lock` とNixの再ビルドを使ってください。`uv run` の自動同期は無効にしています。
ソース修正を直接試す場合は、開発シェル内でチェックアウトのルートから `python webui.py --noautoopen` などを実行できます。
この実行方法は従来どおりチェックアウト側にデータを保存します。

Nix向けPython依存の基準は `pyproject.toml` / `uv.lock` です。
既存の `requirments_*.txt` はWindows・CPU・CUDA 12.8などの従来の手順用です。
共通の依存を変更する場合は、対応する宣言の互換性も確認してください。

### ネイティブライブラリの補修

`nix/python-overrides.nix` でwheelのELFライブラリ参照と、古いwebsocketsのビルド依存を補います。
PyTorchのcuDNN 9とONNX Runtime 1.18のcuDNN 8は異なるSONAMEで共存させています。
同名Pythonパッケージをuvで二重インストールできないため、cuDNN 8だけはハッシュ固定のwheelからNixで取得します。
CUDA Toolkit全体のソースビルドは不要です。

ONNXのTensorRTプロバイダーとTorchaudioのFFmpeg 4/5/6拡張は同梱しません。
RVCの音声読み込みはFFmpeg/FFprobeコマンドにフォールバックし、CUDAでのTorch処理とONNX CUDAプロバイダーは利用できます。

## 検証

`nix flake check` は、GPU・ディスプレイのないNixサンドボックス内で主要モジュールのimport、
音声ファイルの読み書き、FFprobeの実行、モデル保存先を検証します。
実機のGPU確認には `nix run .#doctor`、GUIと音声デバイスの確認には `nix run .#doctor -- --gui` を使います。
実際の音声変換には、事前学習モデルと利用者のRVCモデルが必要です。
