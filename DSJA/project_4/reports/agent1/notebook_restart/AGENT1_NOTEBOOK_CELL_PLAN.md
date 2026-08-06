# Agent 1 Notebook cell plan

agentId = P4-A1-SOURCE
agentName = P4 Source Acquisition & Coverage Engineer

## 00RecoverSourceState.ipynb

- cellStage: `inventory`
- calledModule: `stdlib pathlib/json/hashlib + pandas`
- calledFunctionOrCli: `read-only file and checksum inspection`
- input: existing releases/manifests/raw
- output: display-only inventory
- status: `PLANNABLE_READ_ONLY`
- missingImplementation: project-level recovery module and tests

## 01CollectLinkareerIndex.ipynb

- cellStage: `APQ/month resume`
- calledModule: `NOT_IMPLEMENTED`
- calledFunctionOrCli: `NOT_IMPLEMENTED`
- input: query registry + month
- output: posting_discovery_index
- status: `BLOCKED`
- missingImplementation: APQ builder, httpx policy client, pagination, raw/index store, checkpoint

## 02CollectPostingDetail.ipynb

- cellStage: `detail frontier`
- calledModule: `NOT_IMPLEMENTED`
- calledFunctionOrCli: `NOT_IMPLEMENTED`
- input: global distinct posting IDs
- output: raw HTML + posting manifest
- status: `BLOCKED`
- missingImplementation: frontier, SSR fetch/parser, gzip/raw writer, request manifest

## 03CollectPostingAssets.ipynb

- cellStage: `asset frontier`
- calledModule: `NOT_IMPLEMENTED`
- calledFunctionOrCli: `NOT_IMPLEMENTED`
- input: detail-derived Linkareer asset URLs
- output: asset raw + asset manifest
- status: `BLOCKED`
- missingImplementation: host allowlist, asset classifier/downloader, idempotent manifest

## 04BuildCrawlRelease.ipynb

- cellStage: `validate/stage`
- calledModule: `NOT_IMPLEMENTED`
- calledFunctionOrCli: `sha256sum -c is the only working primitive`
- input: final run manifests
- output: new immutable release
- status: `BLOCKED`
- missingImplementation: release builder, schema validator adapter, Agent 2 validator invocation
