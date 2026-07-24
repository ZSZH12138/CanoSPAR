#!/usr/bin/env sh
set -eu

environment_name=${1:-canospar-week1}
conda_executable=${CONDA_EXE:-conda}

if ! command -v "$conda_executable" >/dev/null 2>&1; then
    printf '%s\n' "Conda was not found. Set CONDA_EXE or add conda to PATH." >&2
    exit 1
fi

"$conda_executable" env create --name "$environment_name" --file environment.yml
"$conda_executable" run --no-capture-output --name "$environment_name" python -m pip check
"$conda_executable" run --no-capture-output --name "$environment_name" python -c 'import torch; assert torch.version.cuda is None; print(torch.__version__)'
