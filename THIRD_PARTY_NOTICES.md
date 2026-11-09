# Third-Party Notices

ConKey includes or depends on the following third-party components. This file
records attribution and license information for the optional voice-typing
feature and the Android client.

## Phonon-2 speech model

- **Component**: Phonon-2 (`FermionResearch/Phonon-2`)
- **Provider**: Fermion Research
- **Used for**: Local, real-time English speech recognition on the laptop CPU
- **License**: Creative Commons Attribution 4.0 International (CC-BY-4.0)
- **Model page**: https://huggingface.co/FermionResearch/Phonon-2
- **License text**: https://creativecommons.org/licenses/by/4.0/legalcode

Phonon-2 is a quantized derivative of NVIDIA's `parakeet-tdt-0.6b-v3`. The
model card and the model container's `NOTICE` describe the changes made by
Fermion Research (five-value quantization and the packed C runtime). The
tokenizer and output conventions originate from the base model. The base model
is also distributed under CC-BY-4.0.

No modifications are made to the model by ConKey. The model is downloaded at
setup time into the user's Fermion cache and is executed by the unmodified
`fermion-research` runtime.

## fermion-research Python package

- **Component**: `fermion-research` (Python package and `fermion` CLI)
- **Provider**: Fermion Research
- **Used for**: Running Phonon-2 locally and serving its streaming WebSocket API
- **License**: Apache License 2.0
- **Project**: https://github.com/fermionresearch/phonon
- **Package**: https://pypi.org/project/fermion-research/

The package is installed at setup time and is not redistributed inside this
repository. It carries its own `LICENSE` and `NOTICE` files in its
distribution metadata.

## Android client dependencies

- **OkHttp** (`com.squareup.okhttp3:okhttp:4.12.0`) — Apache License 2.0,
  https://square.github.io/okhttp/
- **AndroidX Core KTX** (`androidx.core:core-ktx:1.13.1`) — Apache License 2.0,
  https://developer.android.com/jetpack/androidx
- **simple-keyboard** (vendored in the Android assets) — MIT License,
  https://github.com/hodgef/simple-keyboard

## Python host dependencies

- **aiohttp** — Apache License 2.0, https://docs.aiohttp.org/
- **pytest** (development only) — MIT License, https://pytest.org/

Refer to each project's distribution for the complete license text.
