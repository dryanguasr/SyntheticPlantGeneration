# Read copied assembly BRep interference without saving or changing constraints.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$SourceRoot,
      [Parameter(Mandatory=$true)][string]$Assembly,
      [Parameter(Mandatory=$true)][string]$PairsFile,
      [Parameter(Mandatory=$true)][string]$OutputDirectory,
      [string]$MotionFile,
      [switch]$ExportInterferenceGeometry,
      [double]$FacetToleranceM=0.000001)
$ErrorActionPreference='Stop'
$source=[IO.Path]::GetFullPath($SourceRoot)
$path=[IO.Path]::GetFullPath((Join-Path $source $Assembly))
if(-not $path.StartsWith($source.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Assembly escapes copied source root'}
$output=[IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path -LiteralPath $output){throw 'Use a fresh evidence directory'}
[void][IO.Directory]::CreateDirectory($output)
[IO.File]::Copy($PSCommandPath,(Join-Path $output 'script_source.ps1'))
$report=[ordered]@{schema_version='inventor-brep-interference/1.0';status='PREPARING';assembly=$Assembly;
    units=@{length='m';volume='m3'};pairs=@();source_files_unchanged=$false;
    primary_sources=@('https://help.autodesk.com/cloudhelp/2026/ENU/Inventor-API/files/AssemblyComponentDefinition_AnalyzeInterference.htm',
                     'https://help.autodesk.com/cloudhelp/2026/ENU/Inventor-API/files/MeasureTools_GetMinimumDistance.htm');
    scope='Saved native CAD BRep posture, read-only copies; neither modified constraints nor newly validated physical hardware'}
function Save-Report{[IO.File]::WriteAllText((Join-Path $output 'result.json'),($report|ConvertTo-Json -Depth 15),[Text.UTF8Encoding]::new($false))}
function Point-SI($Point){return ,@(([double]$Point.X*0.01),([double]$Point.Y*0.01),([double]$Point.Z*0.01))}
function Matrix-SI($Matrix){
    $values=@();for($r=1;$r -le 4;$r++){for($c=1;$c -le 4;$c++){
        $value=[double]$Matrix.Cell($r,$c);if($c -eq 4 -and $r -le 3){$value*=0.01};$values+=$value
    }};return ,$values
}
function Export-Bodies($Bodies,[string]$Filename,$Transform){
    $destination=Join-Path $output $Filename
    $writer=[IO.StreamWriter]::new($destination,$false,[Text.UTF8Encoding]::new($false))
    $offset=0;$triangles=0;$minimum=@([double]::PositiveInfinity,[double]::PositiveInfinity,[double]::PositiveInfinity)
    $maximum=@([double]::NegativeInfinity,[double]::NegativeInfinity,[double]::NegativeInfinity)
    $nativeMinimum=@([double]::PositiveInfinity,[double]::PositiveInfinity,[double]::PositiveInfinity)
    $nativeMaximum=@([double]::NegativeInfinity,[double]::NegativeInfinity,[double]::NegativeInfinity)
    try{
        $writer.WriteLine('# Native Inventor BRep facets, gripper assembly-local SI metres; diagnostic visualization only')
        foreach($body in $Bodies){
            $range=$body.PreciseRangeBox
            foreach($x in @($range.MinPoint.X,$range.MaxPoint.X)){foreach($y in @($range.MinPoint.Y,$range.MaxPoint.Y)){foreach($z in @($range.MinPoint.Z,$range.MaxPoint.Z)){
                $corner=@(([double]$x*.01),([double]$y*.01),([double]$z*.01))
                for($r=0;$r -lt 3;$r++){
                    $value=$corner[$r]
                    if($null -ne $Transform){$value=[double]$Transform[$r*4+3];for($c=0;$c -lt 3;$c++){$value+=[double]$Transform[$r*4+$c]*$corner[$c]}}
                    $nativeMinimum[$r]=[Math]::Min($nativeMinimum[$r],$value);$nativeMaximum[$r]=[Math]::Max($nativeMaximum[$r],$value)
                }
            }}}
            [int]$vertexCount=0;[int]$facetCount=0
            [double[]]$coordinates=@();[double[]]$normals=@();[int[]]$indices=@()
            $body.CalculateFacets($FacetToleranceM*100,[ref]$vertexCount,[ref]$facetCount,[ref]$coordinates,[ref]$normals,[ref]$indices)
            for($v=0;$v -lt $vertexCount;$v++){
                $xyz=@();for($r=0;$r -lt 3;$r++){
                    $value=[double]$coordinates[$v*3+$r]*.01
                    if($null -ne $Transform){$value=[double]$Transform[$r*4+3];for($c=0;$c -lt 3;$c++){$value+=[double]$Transform[$r*4+$c]*[double]$coordinates[$v*3+$c]*.01}}
                    $minimum[$r]=[Math]::Min($minimum[$r],$value);$maximum[$r]=[Math]::Max($maximum[$r],$value)
                    $xyz+=$value.ToString('G17',[Globalization.CultureInfo]::InvariantCulture)
                };$writer.WriteLine('v '+($xyz -join ' '))
            }
            for($v=0;$v -lt $vertexCount;$v++){
                $normal=@();for($r=0;$r -lt 3;$r++){
                    $value=[double]$normals[$v*3+$r]
                    if($null -ne $Transform){$value=0.;for($c=0;$c -lt 3;$c++){$value+=[double]$Transform[$r*4+$c]*[double]$normals[$v*3+$c]}}
                    $normal+=$value.ToString('G17',[Globalization.CultureInfo]::InvariantCulture)
                };$writer.WriteLine('vn '+($normal -join ' '))
            }
            for($f=0;$f -lt $facetCount;$f++){
                $face=for($a=0;$a -lt 3;$a++){
                    $local=[int]$indices[$f*3+$a];if($local -lt 1 -or $local -gt $vertexCount){throw 'Invalid native facet index'}
                    $index=$offset+$local;"$index//$index"
                };$writer.WriteLine('f '+($face -join ' '))
            };$offset+=$vertexCount;$triangles+=$facetCount
        }
        if(-not $triangles){throw 'No native interference facets'}
    }finally{$writer.Dispose()}
    return @{uri=$Filename;sha256=(Get-FileHash -LiteralPath $destination).Hash.ToLowerInvariant();vertices=$offset;triangles=$triangles;
             chord_tolerance_m=$FacetToleranceM;frame='gripper_assembly_local';units='m';bounds_m=@{min=$minimum;max=$maximum};native_body_range_bounds_m=@{min=$nativeMinimum;max=$nativeMaximum};native_bounds_method='SurfaceBody.PreciseRangeBox'}
}
$application=$null;$document=$null;$sourceDocument=$null;$resolver=$null;$exitCode=1
$files=@(Get-ChildItem -LiteralPath $source -Recurse -File|Where-Object {$_.Extension -in @('.iam','.ipt','.ipj') -and $_.FullName -notmatch '[\\/]OldVersions[\\/]'})
$before=@{};foreach($file in $files){$before[$file.FullName]=(Get-FileHash -LiteralPath $file.FullName).Hash}
$report.assembly_sha256=$before[$path];Save-Report
try{
    if(@(Get-Process -Name Inventor -ErrorAction SilentlyContinue).Count){throw 'Inventor already running; never attach to another owned or user session'}
    $application=New-Object -ComObject Inventor.Application
    $application.Visible=$false;$application.SilentOperation=$true
    $processes=@(Get-Process -Name Inventor)
    if($processes.Count -ne 1){throw 'Cannot establish exclusive application ownership'}
    $report.application=@{pid=$processes[0].Id;version=$application.SoftwareVersion.DisplayVersion}
    $interop=Join-Path (Split-Path $processes[0].Path -Parent) 'Autodesk.Inventor.Interop.dll'
    [void][Reflection.Assembly]::LoadFrom($interop)
    $resolverSource=Join-Path $PSScriptRoot 'inventor_reference_resolver.cs'
    Add-Type -Path $resolverSource -ReferencedAssemblies $interop,'System.Core'
    $resolver=[RealHarvesterCad.ReferenceResolver]::new($application,$source,[string[]]@($files|ForEach-Object FullName))
    $options=$application.TransientObjects.CreateNameValueMap()
    $options.Add('SkipAllUnresolvedFiles',$true);$options.Add('ExpressModeBehavior','OpenFull')
    $report.status='OPENING_COPY';Save-Report
    $document=$application.Documents.OpenWithOptions($path,$options,$false)
    $definition=$document.ComponentDefinition
    $occurrences=@{};foreach($occurrence in $definition.Occurrences){$occurrences[[string]$occurrence.Name]=$occurrence}
    $requests=Get-Content -LiteralPath $PairsFile -Raw -Encoding UTF8|ConvertFrom-Json
    $samples=@(@{driver_rad=0;occurrence_transforms_m=$null})
    if($MotionFile){
        $motion=Get-Content -LiteralPath $MotionFile -Raw -Encoding UTF8|ConvertFrom-Json
        if($motion.assembly_sha256.ToLowerInvariant() -ne $report.assembly_sha256.ToLowerInvariant()){throw 'Motion trace targets a different saved CAD assembly'}
        $sourceDocument=$document
        $document=$application.Documents.Add(12291,'',$false)
        $definition=$document.ComponentDefinition
        $temporary=@{}
        foreach($name in @($requests.pairs|ForEach-Object {$_}|Select-Object -Unique)){
            $original=$occurrences[[string]$name]
            if($null -eq $original){throw ('Missing source occurrence '+$name)}
            $temporary[[string]$name]=$definition.Occurrences.Add($original.Definition.Document.FullFileName,$original.Transformation)
        }
        $occurrences=$temporary;$samples=@($motion.samples)
        $report.motion_file_sha256=(Get-FileHash -LiteralPath $MotionFile).Hash
        $report.motion_scope='Independent temporary assembly with unconstrained copies of named source parts; analytical four-bar rigid transforms only. Original documents and constraints remain untouched.'
    }
    if($ExportInterferenceGeometry -and ($FacetToleranceM -le 0 -or [double]::IsNaN($FacetToleranceM) -or [double]::IsInfinity($FacetToleranceM))){throw 'Facet tolerance must be finite and positive'}
    $sampleIndex=0
    foreach($sample in $samples){
    if($null -ne $sample.occurrence_transforms_m){
        foreach($entry in $sample.occurrence_transforms_m.PSObject.Properties){
            $matrix=$application.TransientGeometry.CreateMatrix()
            for($r=1;$r -le 4;$r++){for($c=1;$c -le 4;$c++){
                $value=[double]$entry.Value[($r-1)*4+$c-1]
                if($c -eq 4 -and $r -le 3){$value*=100}
                $matrix.GetType().InvokeMember('Cell',[Reflection.BindingFlags]::SetProperty,$null,$matrix,@($r,$c,$value))
            }}
            $occurrences[$entry.Name].Transformation=$matrix
        }
        [void]$document.Update2($true)
    }
    $pairIndex=0
    foreach($pair in $requests.pairs){
        $first=$occurrences[[string]$pair[0]];$second=$occurrences[[string]$pair[1]]
        if($null -eq $first -or $null -eq $second){throw ('Requested occurrence absent: '+($pair -join ', '))}
        $row=[ordered]@{driver_rad=$sample.driver_rad;occurrences=@($pair);status='INSPECTING';minimum_distance_m=$null;interference_count=$null;interference_volumes_m3=@()}
        $report.pairs+=,$row;Save-Report
        $distanceContext=$application.TransientObjects.CreateNameValueMap()
        $row.minimum_distance_m=[double]$application.MeasureTools.GetMinimumDistance($first,$second,24833,24833,[ref]$distanceContext)*0.01
        $row.minimum_distance_context=@{}
        foreach($key in @('ClosestPointOne','ClosestPointTwo')){
            try{$row.minimum_distance_context[$key]=Point-SI $distanceContext.Value($key)}catch{}
        }
        $one=$application.TransientObjects.CreateObjectCollection();$one.Add($first)
        $two=$application.TransientObjects.CreateObjectCollection();$two.Add($second)
        $interferences=$definition.AnalyzeInterference($one,$two)
        $row.interference_count=[int]$interferences.Count
        if($ExportInterferenceGeometry){
            $row.visualization_parts=@();$roleIndex=0
            foreach($occurrence in @($first,$second)){
                $bodies=@();for($n=1;$n -le $occurrence.Definition.SurfaceBodies.Count;$n++){$bodies+=,$occurrence.Definition.SurfaceBodies.Item($n)}
                $part=Export-Bodies $bodies ('sample_'+$sampleIndex+'_pair_'+$pairIndex+'_part_'+$roleIndex+'.obj') (Matrix-SI $occurrence.Transformation)
                $part.occurrence=[string]$pair[$roleIndex];$part.role=if($roleIndex -eq 0){'housing'}else{'link'}
                $row.visualization_parts+=,$part;$roleIndex++
            }
            $row.interference_geometry=@()
        }
        for($index=1;$index -le $interferences.Count;$index++){
            $interference=$interferences.Item($index)
            $row.interference_volumes_m3+=([double]$interference.Volume*1e-6)
            if($ExportInterferenceGeometry){
                $body=$interference.InterferenceBody
                $shape=Export-Bodies @($body) ('sample_'+$sampleIndex+'_pair_'+$pairIndex+'_intersection_'+$index+'.obj') $null
                $shape.role='intersection';$shape.centroid_m=Point-SI $interference.Centroid
                $shape.native_bounds_m=@{min=(Point-SI $body.RangeBox.MinPoint);max=(Point-SI $body.RangeBox.MaxPoint)}
                $shape.volume_m3=[double]$interference.Volume*1e-6
                $row.interference_geometry+=,$shape
            }
        }
        $row.status='NATIVE_BREP_OBSERVED';Save-Report
        $pairIndex++
    }
    $sampleIndex++
    }
    $report.status='COMPLETED';$exitCode=0
}catch{$report.status='FAIL';$report.error=$_.Exception.ToString()}
finally{
    if($null -ne $document){$document.Close($true)}
    if($null -ne $sourceDocument){$sourceDocument.Close($true)}
    if($null -ne $resolver){$resolver.Dispose()}
    if($null -ne $application){$application.Quit()}
    $changed=@();foreach($file in $files){if((Get-FileHash -LiteralPath $file.FullName).Hash -ne $before[$file.FullName]){$changed+=$file.FullName}}
    $report.changed_source_files=$changed;$report.source_files_unchanged=($changed.Count -eq 0)
    $report.source_sha256=$before
    $report.script_sha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash
    $report.pairs_file_sha256=(Get-FileHash -LiteralPath $PairsFile).Hash
    Save-Report
}
exit $exitCode
