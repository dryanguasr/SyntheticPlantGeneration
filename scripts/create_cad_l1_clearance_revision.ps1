# Authorized experimental feature in a private CAD copy; never save originals.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$OriginalSourceRoot,
      [Parameter(Mandatory=$true)][string]$RevisionRoot,
      [Parameter(Mandatory=$true)][string]$PlanFile,
      [Parameter(Mandatory=$true)][string]$MotionFile)
$ErrorActionPreference='Stop'
$originalRoot=[IO.Path]::GetFullPath($OriginalSourceRoot)
$revision=[IO.Path]::GetFullPath($RevisionRoot)
$workspace=[IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent)).TrimEnd('\')+'\'
if(-not $revision.StartsWith($workspace,[StringComparison]::OrdinalIgnoreCase)){throw 'Revision must stay in the current workspace'}
if(Test-Path -LiteralPath $revision){throw 'Use a new revision directory; never overwrite earlier CAD evidence'}
$plan=Get-Content -LiteralPath $PlanFile -Raw -Encoding UTF8|ConvertFrom-Json
$motion=Get-Content -LiteralPath $MotionFile -Raw -Encoding UTF8|ConvertFrom-Json
$target=@($motion.samples|Where-Object {[Math]::Abs($_.driver_rad-$plan.target_driver_rad) -lt 1e-12})
if($target.Count -ne 1){throw 'The preregistered target must have exactly one frozen motion transform'}
$targetTransform=@($target[0].occurrence_transforms_m.($plan.occurrence_to_replace))
if($targetTransform.Count -ne 16){throw 'Missing target occurrence transform'}
$originalFiles=@(Get-ChildItem -LiteralPath $originalRoot -Recurse -File|Where-Object {$_.FullName -notmatch '[\\/]OldVersions[\\/]'})
$originalHashes=@{};foreach($file in $originalFiles){$originalHashes[$file.FullName]=(Get-FileHash -LiteralPath $file.FullName).Hash.ToLowerInvariant()}
if($originalHashes[(Join-Path $originalRoot $plan.original_part)] -ne $plan.original_part_sha256){throw 'Original L source revision changed'}
[void][IO.Directory]::CreateDirectory($revision)
[IO.File]::Copy($PSCommandPath,(Join-Path $revision 'script_source.ps1'))
[IO.File]::Copy([IO.Path]::GetFullPath($PlanFile),(Join-Path $revision 'preregistered_plan.json'))
[IO.File]::Copy([IO.Path]::GetFullPath($MotionFile),(Join-Path $revision 'source_motion.json'))
$privateRoot=Join-Path $revision 'source'
Copy-Item -LiteralPath $originalRoot -Destination $privateRoot -Recurse
$privateOriginal=Join-Path $privateRoot $plan.original_part
$privatePart=Join-Path $privateRoot $plan.private_part
[IO.File]::Copy($privateOriginal,$privatePart,$false)
$report=[ordered]@{schema_version='native-cad-local-clearance-revision/1.0';status='PREPARING';
    private_source_root=$privateRoot;original_sources_unchanged=$false;plan=$plan;source_files_sha256=$originalHashes;
    plan_sha256=(Get-FileHash -LiteralPath $PlanFile).Hash.ToLowerInvariant();motion_sha256=(Get-FileHash -LiteralPath $MotionFile).Hash.ToLowerInvariant();
    primary_sources=@('https://help.autodesk.com/cloudhelp/2026/ENU/Inventor-API/files/ComponentOccurrence_Replace.htm',
      'https://help.autodesk.com/cloudhelp/2026/ENU/Inventor-API/files/WorkPlanes_AddFixed.htm',
      'https://help.autodesk.com/cloudhelp/2026/ENU/Inventor-API/files/ExtrudeFeatures_CreateExtrudeDefinition.htm',
      'https://help.autodesk.com/cloudhelp/2026/ENU/Inventor-API/files/ExtrudeDefinition_SetDistanceExtent.htm')}
function Save-Report{[IO.File]::WriteAllText((Join-Path $revision 'revision_report.json'),($report|ConvertTo-Json -Depth 30),[Text.UTF8Encoding]::new($false))}
Save-Report
# Reuse the existing SI/native mass and STEP/OBJ helpers, without its main export.
. (Join-Path $PSScriptRoot 'export_inventor_robot.ps1') -OutputDirectory $revision -ChordToleranceM $plan.mesh_chord_tolerance_m -FunctionsOnly
function Hash-Value([string]$path){return (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()}
function Native-Cylinders($definition){
    $rows=@();$index=0
    foreach($body in $definition.SurfaceBodies){foreach($face in $body.Faces){
        $index++
        if($face.SurfaceType -eq [Inventor.SurfaceTypeEnum]::kCylinderSurface){
            $g=$face.Geometry;$rows+=,@{face_index=$index;radius_m=[double]$g.Radius*.01;
                base_m=(Point-SI $g.BasePoint);axis=(Vector-Values $g.AxisVector)}
        }
    }};return ,$rows
}
function Matrix-Difference($a,$b){$max=0.;for($i=0;$i -lt 16;$i++){$max=[Math]::Max($max,[Math]::Abs($a[$i]-$b[$i]))};return $max}
$application=$null;$resolver=$null;$partDoc=$null;$housingDoc=$null;$assemblyDoc=$null;$armDoc=$null;$exitCode=1
try{
    if(@(Get-Process -Name Inventor -ErrorAction SilentlyContinue).Count){throw 'Inventor already running; do not attach to another session'}
    $application=New-Object -ComObject Inventor.Application
    $application.Visible=$false;$application.SilentOperation=$true
    $processes=@(Get-Process -Name Inventor);if($processes.Count -ne 1){throw 'Cannot establish exclusive Inventor ownership'}
    $report.application=@{pid=$processes[0].Id;version=$application.SoftwareVersion.DisplayVersion}
    $interop=Join-Path (Split-Path $processes[0].Path -Parent) 'Autodesk.Inventor.Interop.dll'
    [void][Reflection.Assembly]::LoadFrom($interop)
    Add-Type -Path (Join-Path $PSScriptRoot 'inventor_reference_resolver.cs') -ReferencedAssemblies $interop,'System.Core'
    $owned=@(Get-ChildItem -LiteralPath $privateRoot -Recurse -File|Where-Object {$_.Extension -in @('.iam','.ipt','.ipj') -and $_.FullName -notmatch '[\\/]OldVersions[\\/]'})
    $resolver=[RealHarvesterCad.ReferenceResolver]::new($application,$privateRoot,[string[]]@($owned|ForEach-Object FullName))
    $options=$application.TransientObjects.CreateNameValueMap();$options.Add('SkipAllUnresolvedFiles',$true);$options.Add('ExpressModeBehavior','OpenFull')
    $report.status='VERIFYING_NATIVE_CUT_PLANE';Save-Report
    $housingDoc=$application.Documents.Open((Join-Path $privateRoot 'gripper/Gripper y engranaje.ipt'),$false)
    $matches=@();$faceIndex=0
    foreach($body in $housingDoc.ComponentDefinition.SurfaceBodies){foreach($face in $body.Faces){
        $faceIndex++
        if($face.SurfaceType -ne [Inventor.SurfaceTypeEnum]::kPlaneSurface){continue}
        $geometry=$face.Geometry;$normal=Vector-Values $geometry.Normal;$point=Point-SI $geometry.RootPoint
        $dot=0.;for($i=0;$i -lt 3;$i++){$dot+=$normal[$i]*$plan.expected_housing_plane_normal[$i]}
        if([Math]::Abs($dot) -lt .999999999){continue}
        if($dot -lt 0){$normal=@($normal|ForEach-Object {-$_})}
        $offset=0.;for($i=0;$i -lt 3;$i++){$offset+=$normal[$i]*$point[$i]}
        if([Math]::Abs($offset-$plan.expected_housing_plane_offset_m) -le $plan.native_plane_match_tolerance_m){
            $matches+=,@{face_index=$faceIndex;normal=$normal;point_m=$point;offset_m=$offset}
        }
    }}
    if(-not $matches.Count){throw 'No exact native housing plane matches the preregistered diagnostic surface'}
    $nativePlane=$matches[0]
    foreach($p in $matches){if([Math]::Abs($p.offset_m-$nativePlane.offset_m) -gt 1e-10){throw 'Ambiguous native relief reference planes'}}
    $report.native_matching_planes=$matches
    $normalLocal=@(0.,0.,0.);$offsetLocal=[double]$nativePlane.offset_m-[double]$plan.CAD_clearance_reserve_m
    for($r=0;$r -lt 3;$r++){
        $offsetLocal-=$nativePlane.normal[$r]*$targetTransform[$r*4+3]
        for($c=0;$c -lt 3;$c++){$normalLocal[$c]+=$targetTransform[$r*4+$c]*$nativePlane.normal[$r]}
    }
    if([Math]::Abs($normalLocal[1]) -gt 1e-9){throw 'Relief is not in the agreed XZ extrusion plane'}
    $ligament=$offsetLocal-[double]$plan.pin_hole_radius_m
    if($ligament -lt $plan.minimum_geometric_ligament_m){throw 'Preregistered minimum geometric ligament would be violated'}
    $report.native_reference_plane=$nativePlane
    $report.cut_geometry=@{normal_local=$normalLocal;offset_local_m=$offsetLocal;ligament_to_pin_hole_m=$ligament;
        target_occurrence_transform_m=$targetTransform;clearance_reserve_m=$plan.CAD_clearance_reserve_m}
    $partDoc=$application.Documents.Open($privatePart,$false)
    $definition=$partDoc.ComponentDefinition;$beforeMass=Get-MassRecord $definition;$beforeCylinders=Native-Cylinders $definition
    if($beforeMass.status -ne 'derivado_de_CAD' -or $beforeMass.mass_overridden){throw 'Need native non-overridden material mass before editing'}
    $pin=@($beforeCylinders|Where-Object {[Math]::Abs($_.radius_m-$plan.pin_hole_radius_m) -lt 1e-10 -and
        [Math]::Abs($_.base_m[0]) -lt 1e-10 -and [Math]::Abs($_.base_m[2]) -lt 1e-10 -and [Math]::Abs($_.axis[1]) -gt .999999999})
    if(-not $pin.Count){throw 'Preregistered pin hole not found in native part'}
    $report.before_mass_properties=$beforeMass;$report.before_cylinders=$beforeCylinders
    $report.status='CREATING_PRIVATE_LOCAL_CUT';Save-Report
    $tg=$application.TransientGeometry
    $cutPlanes=@(@{name=$plan.feature_name;normal_local=$normalLocal;offset_local_m=$offsetLocal})
    foreach($extra in @($plan.additional_local_cuts)){
        if($null -eq $extra){continue}
        $n=@($extra.normal_local);$length=[Math]::Sqrt($n[0]*$n[0]+$n[1]*$n[1]+$n[2]*$n[2])
        if($n.Count -ne 3 -or [Math]::Abs($length-1) -gt 1e-10 -or [Math]::Abs($n[1]) -gt 1e-10){throw 'Additional relief needs an explicit unit XZ normal'}
        if([double]$extra.offset_local_m-$plan.pin_hole_radius_m -lt $plan.minimum_geometric_ligament_m){throw 'Additional local relief would violate the unchanged minimum ligament'}
        $cutPlanes+=,@{name=$extra.name;normal_local=$n;offset_local_m=[double]$extra.offset_local_m}
    }
    $report.actual_cut_planes=$cutPlanes
    foreach($cut in $cutPlanes){
    $plane=$definition.WorkPlanes.AddFixed($tg.CreatePoint(0,0,0),$tg.CreateUnitVector(1,0,0),$tg.CreateUnitVector(0,0,1),$false)
    $plane.Name=$cut.name+'_plane';$plane.Visible=$false
    $sketch=$definition.Sketches.Add($plane);$sketch.Name=$cut.name+'_profile'
    $nx=$cut.normal_local[0];$nz=$cut.normal_local[2];$tx=-$nz;$tz=$nx
    $corners=@();foreach($pair in @(@($cut.offset_local_m,-$plan.local_cut_tangent_halfwidth_m),@($plan.local_cut_normal_extent_m,-$plan.local_cut_tangent_halfwidth_m),@($plan.local_cut_normal_extent_m,$plan.local_cut_tangent_halfwidth_m),@($cut.offset_local_m,$plan.local_cut_tangent_halfwidth_m))){
        $modelPoint=$tg.CreatePoint(100*($nx*$pair[0]+$tx*$pair[1]),0,100*($nz*$pair[0]+$tz*$pair[1]))
        $corners+=,$sketch.ModelToSketchSpace($modelPoint)
    }
    $firstLine=$sketch.SketchLines.AddByTwoPoints($corners[0],$corners[1]);$previousLine=$firstLine
    for($i=1;$i -lt 3;$i++){$previousLine=$sketch.SketchLines.AddByTwoPoints($previousLine.EndSketchPoint,$corners[$i+1])}
    [void]$sketch.SketchLines.AddByTwoPoints($previousLine.EndSketchPoint,$firstLine.StartSketchPoint)
    $report.native_sketch_vertices_cm=@($sketch.SketchPoints|ForEach-Object {@([double]$_.Geometry.X,[double]$_.Geometry.Y)})
    Save-Report
    $cutProfile=$sketch.Profiles.AddForSolid($true)
    $extrude=$definition.Features.ExtrudeFeatures.CreateExtrudeDefinition($cutProfile,[Inventor.PartFeatureOperationEnum]::kCutOperation)
    $extrude.SetDistanceExtent([double]$plan.symmetric_extrusion_distance_m*100,[Inventor.PartFeatureExtentDirectionEnum]::kSymmetricExtentDirection)
    $feature=$definition.Features.ExtrudeFeatures.Add($extrude);$feature.Name=$cut.name;$sketch.Visible=$false
    if(-not $partDoc.Update2($true)){throw 'Native cut feature did not update successfully'}
    }
    $afterMass=Get-MassRecord $definition;$afterCylinders=Native-Cylinders $definition
    $removed=[double]$beforeMass.volume_m3-[double]$afterMass.volume_m3
    if($removed -le 0 -or $removed/$beforeMass.volume_m3 -gt $plan.maximum_removed_fraction_of_part_volume){throw 'Unexpected amount of material removed'}
    $afterPin=@($afterCylinders|Where-Object {[Math]::Abs($_.radius_m-$plan.pin_hole_radius_m) -lt 1e-10 -and [Math]::Abs($_.base_m[0]) -lt 1e-10 -and [Math]::Abs($_.base_m[2]) -lt 1e-10 -and [Math]::Abs($_.axis[1]) -gt .999999999})
    if($afterPin.Count -ne $pin.Count){throw 'Pin cylinder identity geometry changed'}
    $report.after_mass_properties=$afterMass;$report.after_cylinders=$afterCylinders
    $report.removed_volume_m3=$removed;$report.removed_mass_kg=$beforeMass.mass_kg-$afterMass.mass_kg
    $report.material_density_kg_m3=$afterMass.mass_kg/$afterMass.volume_m3
    $report.feature=@{name=[string]$feature.Name;health=[int]$feature.HealthStatus;type='native_extrude_cut';pin_hole_preserved=$true;native_material_unchanged=$true}
    $partDoc.Save2($false)
    $report.part_obj=Export-Facets $definition (Join-Path $revision 'L1_clearance_document_local.obj')
    Export-Step $partDoc (Join-Path $revision 'L1_clearance_rev01.step')
    $partDoc.Close($true);$partDoc=$null
    $report.status='REPLACING_ONLY_L1_IN_PRIVATE_ASSEMBLY';Save-Report
    $assemblyPath=Join-Path $privateRoot $plan.gripper_assembly
    $assemblyDoc=$application.Documents.OpenWithOptions($assemblyPath,$options,$false)
    $occurrences=@{};foreach($occ in $assemblyDoc.ComponentDefinition.Occurrences){$occurrences[[string]$occ.Name]=$occ}
    $replace=$occurrences[$plan.occurrence_to_replace];$preserve=$occurrences[$plan.occurrence_to_preserve]
    $savedTransforms=@{};foreach($name in $occurrences.Keys){$savedTransforms[$name]=Convert-MatrixToSI $occurrences[$name].Transformation}
    $report.constraints_before=Get-Relations $assemblyDoc.ComponentDefinition
    $replace.Replace($privatePart,$false);$replace.Name=$plan.occurrence_to_replace
    if(-not $assemblyDoc.Update2($true)){throw 'Private gripper constraints failed after one-occurrence replacement'}
    $maximum=0.;foreach($name in $occurrences.Keys){$maximum=[Math]::Max($maximum,(Matrix-Difference $savedTransforms[$name] (Convert-MatrixToSI $occurrences[$name].Transformation)))}
    if($maximum -gt 1e-8){throw 'Saved assembly reference placements changed after replacement'}
    if([IO.Path]::GetFullPath($preserve.Definition.Document.FullFileName) -ne [IO.Path]::GetFullPath($privateOriginal)){throw 'L2 no longer references the untouched original part'}
    if((Hash-Value $privateOriginal) -ne $plan.original_part_sha256){throw 'Shared L2 part bytes changed'}
    $report.constraints_after=Get-Relations $assemblyDoc.ComponentDefinition
    $report.maximum_saved_assembly_transform_change=$maximum
    $report.occurrence_binding=@{L1=$replace.Definition.Document.FullFileName;L2=$preserve.Definition.Document.FullFileName;
        L1_transform_m=(Convert-MatrixToSI $replace.Transformation);L2_transform_m=(Convert-MatrixToSI $preserve.Transformation);
        L2_source_sha256=(Hash-Value $privateOriginal);full_robot_part_index=104;unchanged_full_robot_L2_index=106}
    $assemblyDoc.Save2($false)
    Export-Step $assemblyDoc (Join-Path $revision 'gripper_clearance_reference.step')
    $report.status='VERIFYING_FULL_ARM_REFERENCE';Save-Report
    $armPath=Join-Path $privateRoot $plan.arm_assembly
    $armDoc=$application.Documents.OpenWithOptions($armPath,$options,$false)
    $gripper=@($armDoc.ComponentDefinition.Occurrences|Where-Object {$_.Name -eq 'Gripper ensamble:1'})
    if($gripper.Count -ne 1 -or [IO.Path]::GetFullPath($gripper[0].Definition.Document.FullFileName) -ne [IO.Path]::GetFullPath($assemblyPath)){throw 'Copied arm did not resolve the revised private gripper assembly'}
    $nested=@($gripper[0].Definition.Occurrences|Where-Object {$_.Name -eq $plan.occurrence_to_replace})
    if($nested.Count -ne 1 -or [IO.Path]::GetFullPath($nested[0].Definition.Document.FullFileName) -ne [IO.Path]::GetFullPath($privatePart)){throw 'Full-arm part104 does not bind the dedicated L1 revision'}
    [void]$armDoc.Update2($true);$armDoc.Save2($false)
    $report.full_arm_reference=@{assembly=$armPath;gripper_document=$assemblyPath;private_L1_document=$privatePart;
        gripper_transform_in_arm_m=(Convert-MatrixToSI $gripper[0].Transformation);status='PRIVATE_CHAIN_VERIFIED'}
    $report.status='EXPORTED_PENDING_INDEPENDENT_SWEEP';$exitCode=0
}catch{$report.status='FAIL';$report.error=$_.Exception.ToString();$report.script_stack_trace=$_.ScriptStackTrace}
finally{
    foreach($document in @($armDoc,$assemblyDoc,$partDoc,$housingDoc)){if($null -ne $document){try{$document.Close($true)}catch{}}}
    if($null -ne $resolver){$report.reference_resolution=$resolver.Records;$resolver.Dispose()}
    if($null -ne $application){$application.Quit()}
    $changed=@();foreach($file in $originalFiles){if((Hash-Value $file.FullName) -ne $originalHashes[$file.FullName]){$changed+=$file.FullName}}
    $report.changed_original_sources=$changed;$report.original_sources_unchanged=($changed.Count -eq 0)
    $report.final_L2_copy_sha256=Hash-Value $privateOriginal
    if($changed.Count -or $report.final_L2_copy_sha256 -ne $plan.original_part_sha256){$report.status='FAIL_SOURCE_INTEGRITY';$exitCode=1}
    $outputs=@{};foreach($file in @(Get-ChildItem -LiteralPath $revision -File -Recurse|Where-Object {$_.FullName -notmatch '[\\/]OldVersions[\\/]' -and $_.Name -ne 'revision_report.json'})){$outputs[$file.FullName.Substring($revision.Length+1).Replace('\','/')]=Hash-Value $file.FullName}
    $report.artifact_sha256=$outputs;$report.script_sha256=Hash-Value (Join-Path $revision 'script_source.ps1')
    Save-Report
}
exit $exitCode
