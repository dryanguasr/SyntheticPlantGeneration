# Pure unit/frame checks; these are NOT a CAD opening or Inventor acceptance test.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../scripts/export_inventor_robot.ps1') -OutputDirectory . -FunctionsOnly
function Assert-Near($Actual,$Expected,[string]$Name){
    if([math]::Abs($Actual-$Expected) -gt 1e-10){throw "$Name : expected $Expected, got $Actual"}
}
$matrix=[pscustomobject]@{data=@(0.,-1.,0.,100.,1.,0.,0.,200.,0.,0.,1.,300.,0.,0.,0.,1.)}
$matrix|Add-Member ScriptMethod Cell {param($r,$c);return $this.data[($r-1)*4+$c-1]}
$si=Convert-MatrixToSI $matrix
Assert-Near $si[3] 1 'cm to metres X'
Assert-Near $si[7] 2 'cm to metres Y'
Assert-Near $si[11] 3 'cm to metres Z'
Assert-Near $si[1] -1 'Rotation must not be scaled'
$local=@(1.,0.,0.,.5,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
$root=Join-Transforms $si $local
Assert-Near $root[3] 1 'Parent rotation applies to child translation X'
Assert-Near $root[7] 2.5 'Parent rotation applies to child translation Y'
Assert-Near $root[15] 1 'Homogeneous matrix'
$point=Point-SI ([pscustomobject]@{X=50.;Y=-25.;Z=100.})
Assert-Near $point[0] .5 'Point X conversion'
Assert-Near $point[1] -.25 'Point Y conversion'
$missingRejected=$false
try{Point-SI $null}catch{$missingRejected=$true}
if(-not $missingRejected){throw 'Unavailable CAD point must not become a zero point'}
$mass=[pscustomobject]@{Mass=2.;Volume=1000000.;Area=60000.;CenterOfMass=([pscustomobject]@{X=50.;Y=0.;Z=0.});CacheResultsOnCompute=$true;MassOverridden=$false;VolumeOverridden=$false}
$mass|Add-Member ScriptMethod XYZMomentsOfInertia {param($xx,$yy,$zz,$xy,$yz,$xz);$xx.Value=10000./3;$yy.Value=10000./3;$zz.Value=10000./3;$xy.Value=0.;$yz.Value=0.;$xz.Value=0.}
$mass|Add-Member ScriptMethod PrincipalMomentsOfInertia {param($a,$b,$c);$a.Value=10000./3;$b.Value=10000./3;$c.Value=10000./3}
$record=Get-MassRecord ([pscustomobject]@{MassProperties=$mass})
if($record.status -ne 'derivado_de_CAD'){throw $record.error}
Assert-Near $record.mass_kg 2 'Database kg unchanged'
Assert-Near $record.volume_m3 1 'Cubic centimetres to cubic metres'
Assert-Near $record.area_m2 6 'Square centimetres to square metres'
Assert-Near $record.xyz_moments_kg_m2[0] (1./3) '2 kg unit-cube inertia conversion'
if($mass.CacheResultsOnCompute){throw 'Mass-property caching must be disabled'}
$asymmetric=@((25./9),(22./9),(16./9),(-10./9),(-8./9),(2./9))
$check=Test-InertiaConsistency $asymmetric @(1.,2.,4.)
if(-not $check.consistent){throw 'Known asymmetric rotated tensor failed principal invariants'}
$wrongSign=@($asymmetric[0],$asymmetric[1],$asymmetric[2],(-$asymmetric[3]),(-$asymmetric[4]),(-$asymmetric[5]))
if((Test-InertiaConsistency $wrongSign @(1.,2.,4.)).consistent){throw 'Wrong cross-term signs were accepted'}
$script:SourcePrefix=[IO.Path]::GetFullPath('C:/cad/copied').TrimEnd('\')+'\'
if(-not(Within-Source 'C:/cad/copied/part.ipt')){throw 'Internal source rejected'}
if(Within-Source 'C:/cad/copied_other/part.ipt'){throw 'Sibling source incorrectly admitted'}
if(Within-Source 'C:/cad/copied/../original/part.ipt'){throw 'Traversal source incorrectly admitted'}
Write-Output 'PASS: SI conversion, parent/local frame composition, cube mass properties, asymmetric inertia invariants/sign rejection, source-root boundary (pure helpers only).'
