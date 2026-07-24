[CmdletBinding()]
param(
    [string]$EnvironmentName = "canospar-week1"
)

$ErrorActionPreference = "Stop"
$condaExecutable = if ($env:CONDA_EXE) {
    $env:CONDA_EXE
} else {
    $command = Get-Command conda -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "Conda was not found. Set CONDA_EXE or add conda to PATH."
    }
    $command.Source
}

& $condaExecutable env create --name $EnvironmentName --file environment.yml
& $condaExecutable run --no-capture-output --name $EnvironmentName python -m pip check
& $condaExecutable run --no-capture-output --name $EnvironmentName python -c "import torch; assert torch.version.cuda is None; print(torch.__version__)"
