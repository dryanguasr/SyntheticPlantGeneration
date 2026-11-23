# Export copied Inventor sources without saving their documents. Windows PowerShell -STA.
[CmdletBinding()]
param(
    [string]$SourceRoot,
    [string[]]$Assemblies = @(),
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [double]$ChordToleranceM = 0.0002,
    [string]$GeneratedMembersManifest,
    [switch]$SkipGeometry,
    [switch]$ProbeOnly,
    [switch]$FunctionsOnly
)
$ErrorActionPreference = 'Stop'
$script:Invariant = [Globalization.CultureInfo]::InvariantCulture
function Get-FileHash([string]$LiteralPath, [string]$Algorithm='SHA256') {
    # Do not depend on the launcher inheriting a compatible PSModulePath.
    $stream=[IO.File]::OpenRead($LiteralPath); $hasher=[Security.Cryptography.SHA256]::Create()
    try{return @{Hash=([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-','').ToLowerInvariant()}}
    finally{$stream.Dispose();$hasher.Dispose()}
}

function Convert-MatrixToSI($Matrix) {
    $values = [double[]]::new(16)
    for ($r=1; $r -le 4; $r++) { for ($c=1; $c -le 4; $c++) {
        $value = [double]$Matrix.Cell($r,$c)
        if ($c -eq 4 -and $r -le 3) { $value *= 0.01 }
        $values[($r-1)*4+$c-1] = $value
    } }
    return ,$values
}
function Join-Transforms($Parent, $Local) {
    $result = [double[]]::new(16)
    for ($r=0; $r -lt 4; $r++) { for ($c=0; $c -lt 4; $c++) {
        for ($k=0; $k -lt 4; $k++) { $result[$r*4+$c] += $Parent[$r*4+$k]*$Local[$k*4+$c] }
    } }
    return ,$result
}
function Point-SI($Point) {
    if($null -eq $Point -or $null -eq $Point.X -or $null -eq $Point.Y -or $null -eq $Point.Z){throw 'Point unavailable; do not substitute zero'}
    return ,@(([double]$Point.X*0.01),([double]$Point.Y*0.01),([double]$Point.Z*0.01))
}
function Vector-Values($Vector) {
    if($null -eq $Vector -or $null -eq $Vector.X -or $null -eq $Vector.Y -or $null -eq $Vector.Z){throw 'Vector unavailable; do not substitute zero'}
    return ,@([double]$Vector.X,[double]$Vector.Y,[double]$Vector.Z)
}
function Try-Scalar($Object, [string]$Name) {
    try {
        $value = $Object.$Name
        if ($null -eq $value -or $value -is [string] -or $value -is [ValueType]) { return $value }
        return $null
    } catch { return $null }
}
function Get-AppearanceRecord($Asset) {
    if($null -eq $Asset){return @{status='unavailable';reason='No appearance asset exposed'}}
    try{
        $record=[ordered]@{status='asset_values_read';name=[string]$Asset.Name;display_name=[string]$Asset.DisplayName;has_texture=[bool]$Asset.HasTexture;colors=[ordered]@{};scalar_values=[ordered]@{};diffuse_status='unmapped_asset_shader';color_encoding='native byte RGB normalized to 0..1; no colorimetric calibration';limitations=@('Document/occurrence appearance values only; face overrides and textures are not baked into OBJ','Native shader parameters do not establish an exact Gazebo PBR shader equivalence')}
        for($i=1;$i -le $Asset.Count;$i++){
            $value=$Asset.Item($i);$name=[string]$value.Name
            if([int]$value.ValueType -eq 99335){
                $color=$value.Value
                $record.colors[$name]=@{rgb_255=@([int]$color.Red,[int]$color.Green,[int]$color.Blue);rgb=@(([double]$color.Red/255),([double]$color.Green/255),([double]$color.Blue/255));opacity=(Try-Scalar $color 'Opacity');has_connected_texture=[bool]$value.HasConnectedTexture;has_multiple_values=[bool]$value.HasMultipleValues}
            }elseif([int]$value.ValueType -in @(99329,99330,99331,99332,99333,99334)){$record.scalar_values[$name]=Try-Scalar $value 'Value'}
        }
        foreach($name in @('generic_diffuse','metal_color','metallicpaint_base_color','plastic_vinyl_color','opaque_albedo','ceramic_color','wallpaint_color')){
            if($record.colors.Contains($name)){
                $record.diffuse_property=$name
                if($record.colors[$name].has_connected_texture){$record.diffuse_status='texture_overrides_color_value'}
                elseif($record.colors[$name].has_multiple_values){$record.diffuse_status='multiple_values_require_mapping'}
                else{$record.diffuse_status='native_rgb';$record.diffuse_rgb=$record.colors[$name].rgb}
                break
            }
        }
        return $record
    }catch{return @{status='unavailable';error=$_.Exception.Message}}
}
function Within-Source([string]$Path) {
    if (-not $Path) { return $false }
    $full = [IO.Path]::GetFullPath($Path)
    return $full.StartsWith($script:SourcePrefix,[StringComparison]::OrdinalIgnoreCase)
}
function Source-Relative([string]$Path) {
    if (Within-Source $Path) { return [IO.Path]::GetFullPath($Path).Substring($script:SourcePrefix.Length).Replace('\','/') }
    return $null
}
function Write-Inventory {
    $json=$script:Report|ConvertTo-Json -Depth 40
    for($attempt=0;$attempt -lt 10;$attempt++){
        try{[IO.File]::WriteAllText((Join-Path $script:Output 'cad_inventory.json'),$json,[Text.UTF8Encoding]::new($true));return}
        catch{if($attempt -eq 9){throw};Start-Sleep -Milliseconds 100}
    }
}
function Add-Issue([string]$Scope, [string]$Message) {
    [void]$script:Report.issues.Add([ordered]@{scope=$Scope;message=$Message})
}
function Test-InertiaConsistency($XYZ, $Principal) {
    $a,$b,$c,$d,$e,$f=$XYZ # xx,yy,zz,xy,yz,xz
    $p,$q,$r=$Principal
    $tensor=@(($a+$b+$c),($a*$b+$a*$c+$b*$c-$d*$d-$e*$e-$f*$f),($a*$b*$c+2*$d*$e*$f-$a*$e*$e-$b*$f*$f-$c*$d*$d))
    $eigenvalues=@(($p+$q+$r),($p*$q+$p*$r+$q*$r),($p*$q*$r))
    $errors=@();for($i=0;$i -lt 3;$i++){$errors+=([math]::Abs($tensor[$i]-$eigenvalues[$i])/[math]::Max([math]::Abs($eigenvalues[$i]),1e-300))}
    return @{consistent=(($errors|Measure-Object -Maximum).Maximum -lt 1e-6);relative_errors=$errors;invariants=@('trace','second_principal_invariant','determinant');tolerance=1e-6}
}
function Get-MassRecord($Definition) {
    try {
        $mass = $Definition.MassProperties
        $mass.CacheResultsOnCompute = $false
        [double]$xx=0; [double]$yy=0; [double]$zz=0; [double]$xy=0; [double]$yz=0; [double]$xz=0
        $mass.XYZMomentsOfInertia([ref]$xx,[ref]$yy,[ref]$zz,[ref]$xy,[ref]$yz,[ref]$xz)
        [double]$p1=0; [double]$p2=0; [double]$p3=0
        $mass.PrincipalMomentsOfInertia([ref]$p1,[ref]$p2,[ref]$p3)
        $xyz=@(($xx*0.0001),($yy*0.0001),($zz*0.0001),($xy*0.0001),($yz*0.0001),($xz*0.0001))
        $principal=@(($p1*0.0001),($p2*0.0001),($p3*0.0001))
        $consistency=Test-InertiaConsistency $xyz $principal
        return [ordered]@{
            status='derivado_de_CAD'; mass_kg=[double]$mass.Mass
            volume_m3=[double]$mass.Volume*0.000001; area_m2=[double]$mass.Area*0.0001
            center_of_mass_m=(Point-SI $mass.CenterOfMass)
            xyz_moments_kg_m2=$xyz
            xyz_order=@('Ixx','Iyy','Izz','Ixy','Iyz','Ixz')
            principal_moments_kg_m2=$principal
            inertia_frame='document axes through CAD center of mass'
            off_diagonal_convention='direct symmetric tensor entries; reorder raw xx,yy,zz,xy,yz,xz to SDF xx,xy,xz,yy,yz,zz; do not negate'
            tensor_principal_consistency=$consistency
            completeness='loaded CAD only; unresolved components make assembly totals incomplete'
            mass_overridden=(Try-Scalar $mass 'MassOverridden')
            volume_overridden=(Try-Scalar $mass 'VolumeOverridden')
            hardware_validation='pending; CAD material density/solid geometry may differ from printed or purchased parts'
        }
    } catch { return @{status='unavailable';error=$_.Exception.Message} }
}
function Get-GeometryRecord($Entity) {
    if ($null -eq $Entity) { return @{status='unavailable'} }
    $result = [ordered]@{type_code=(Try-Scalar $Entity 'Type')}
    try { $result.point_m = Point-SI $Entity.Point } catch {}
    try { $geometry = $Entity.Geometry } catch { $geometry = $Entity }
    if ($null -eq $geometry) { $geometry = $Entity }
    foreach ($name in @('RootPoint','BasePoint','Center')) {
        try { $result[$name+'_m'] = Point-SI $geometry.$name } catch {}
    }
    foreach ($name in @('Direction','AxisVector','Normal')) {
        try { $result[$name] = Vector-Values $geometry.$name } catch {}
    }
    return $result
}
function Get-Relations($Definition) {
    $result = [Collections.Generic.List[object]]::new()
    foreach ($collectionName in @('Constraints','Joints')) {
        try { $items = $Definition.$collectionName; $count = $items.Count } catch { continue }
        for ($i=1; $i -le $count; $i++) {
            $item = $items.Item($i)
            $row = [ordered]@{collection=$collectionName;name=(Try-Scalar $item 'Name');type_code=(Try-Scalar $item 'Type');suppressed=(Try-Scalar $item 'Suppressed');health_status=(Try-Scalar $item 'HealthStatus')}
            foreach ($side in @('OccurrenceOne','OccurrenceTwo')) {
                try { $row[$side] = $item.$side.Name } catch { $row[$side] = $null }
            }
            $definition = $item
            if ($collectionName -eq 'Joints') { try { $definition = $item.Definition } catch {} }
            foreach ($name in @('JointType','FlipAlignmentDirection','FlipOriginDirection','HasAngularPositionLimits','HasLinearPositionStartLimit','HasLinearPositionEndLimit')) {
                $row[$name] = Try-Scalar $definition $name
            }
            $parameters = [ordered]@{}
            foreach ($name in @('Offset','Angle','Gap','AngularPosition','AngularPositionStartLimit','AngularPositionEndLimit','LinearPosition','LinearPositionStartLimit','LinearPositionEndLimit')) {
                try {
                    $parameter = $definition.$name
                    if ($null -eq $parameter) { continue }
                    if ($parameter -is [ValueType]) { $parameters[$name]=@{database_value=$parameter} }
                    else { $parameters[$name]=@{database_value=$parameter.Value;display_units=$parameter.Units;expression=$parameter.Expression} }
                    $angular=$name -match 'Angle|Angular'
                    $factor=if($angular){1.0}else{0.01}
                    $parameters[$name].si_value=[double]$parameters[$name].database_value*$factor
                    $parameters[$name].si_unit=if($angular){'rad'}else{'m'}
                } catch {}
            }
            $row.parameters = $parameters
            foreach ($name in @('EntityOne','EntityTwo','OriginOne','OriginTwo','AlignmentOne','AlignmentTwo')) {
                try { $row[$name] = Get-GeometryRecord $definition.$name } catch {}
            }
            $row.robot_joint_mapping = 'pending; assembly constraints are not automatically robot joints'
            [void]$result.Add($row)
        }
    }
    return ,$result.ToArray()
}
function Export-Facets($Definition, [string]$Destination) {
    $writer = [IO.StreamWriter]::new($Destination,$false,[Text.UTF8Encoding]::new($false))
    $vertexOffset=0; $triangles=0
    try {
        $writer.WriteLine('# Inventor CalculateFacets; document-local metres; original CAD appearance not reproduced')
        for ($bodyIndex=1; $bodyIndex -le $Definition.SurfaceBodies.Count; $bodyIndex++) {
            $body=$Definition.SurfaceBodies.Item($bodyIndex)
            [int]$vertexCount=0; [int]$facetCount=0
            [double[]]$coordinates=@(); [double[]]$normals=@(); [int[]]$indices=@()
            $body.CalculateFacets($ChordToleranceM*100,[ref]$vertexCount,[ref]$facetCount,[ref]$coordinates,[ref]$normals,[ref]$indices)
            $writer.WriteLine('o body_'+$bodyIndex)
            for ($v=0; $v -lt $vertexCount; $v++) {
                $xyz=for($a=0;$a -lt 3;$a++){ ([double]$coordinates[$v*3+$a]*0.01).ToString('G17',$script:Invariant) }
                $writer.WriteLine('v '+($xyz -join ' '))
            }
            for ($v=0; $v -lt $vertexCount; $v++) {
                $normal=for($a=0;$a -lt 3;$a++){ ([double]$normals[$v*3+$a]).ToString('G17',$script:Invariant) }
                $writer.WriteLine('vn '+($normal -join ' '))
            }
            for($f=0;$f -lt $facetCount;$f++) {
                $face=for($a=0;$a -lt 3;$a++){
                    $local=[int]$indices[$f*3+$a]
                    if($local -lt 1 -or $local -gt $vertexCount){throw 'Invalid 1-based Inventor facet index'}
                    $index=$vertexOffset+$local; "$index//$index"
                }
                $writer.WriteLine('f '+($face -join ' '))
            }
            $vertexOffset+=$vertexCount; $triangles+=$facetCount
        }
        if($triangles -eq 0){throw 'No surface facets returned'}
    } finally { $writer.Dispose() }
    return @{vertices=$vertexOffset;triangles=$triangles;chord_tolerance_m=$ChordToleranceM;units='m';frame='document_local'}
}
function Export-Step($Document,[string]$Destination) {
    $translator=$script:Application.ApplicationAddIns.ItemById('{90AF7F40-0C01-11D5-8E83-0010B541CD80}')
    if(-not $translator.Activated){$translator.Activate()}
    $context=$script:Application.TransientObjects.CreateTranslationContext()
    $context.Type=13059 # kFileBrowseIOMechanism
    $options=$script:Application.TransientObjects.CreateNameValueMap()
    if(-not $translator.HasSaveCopyAsOptions($Document,$context,$options)){throw 'STEP translator unavailable for document'}
    $options.Value('ApplicationProtocolType')=3 # AP214, official Inventor sample
    $medium=$script:Application.TransientObjects.CreateDataMedium()
    $medium.FileName=$Destination
    $translator.SaveCopyAs($Document,$context,$options,$medium)
}
function Register-Document($Document) {
    $path=[string]$Document.FullFileName
    if(-not(Within-Source $path)){Add-Issue 'external_reference' $path; return $null}
    $key=[string]$Document.FullDocumentName
    if($script:Documents.ContainsKey($key)){return $script:Documents[$key].id}
    $hash=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    $id='doc_'+$script:Documents.Count.ToString('D5')
    $row=[ordered]@{id=$id;source_path=(Source-Relative $path);full_document_name=$key;sha256=$hash;internal_name=$Document.InternalName;document_type=[int]$Document.DocumentType;references=@();exports=[ordered]@{};status='inspecting'}
    if($script:GeneratedMembers.ContainsKey($hash)){$row.provenance=@{kind='GeneratedContentCenter';member=$script:GeneratedMembers[$hash];original_referenced_identity=$false}}
    $script:Documents[$key]=$row
    [void]$script:Report.documents.Add($row)
    $references=[Collections.Generic.List[object]]::new()
    foreach($descriptor in $Document.ReferencedDocumentDescriptors){
        $reference=[ordered]@{name=$descriptor.DisplayName;full_name=$descriptor.FullDocumentName;missing=$descriptor.ReferenceMissing;suppressed=$descriptor.ReferenceSuppressed;disabled=$descriptor.ReferenceDisabled}
        try{$reference.source_path=Source-Relative $descriptor.ReferencedFileDescriptor.FullFileName}catch{}
        if($reference.missing -and -not $reference.suppressed){Add-Issue 'unresolved_reference' ([string]$reference.full_name)}
        [void]$references.Add($reference)
    }
    $row.references=$references.ToArray()
    $definition=$Document.ComponentDefinition
    $noSurfaceGeometry=$false
    if([int]$Document.DocumentType -eq 12290){
        $row.geometry_inventory=[ordered]@{surface_bodies=[int]$definition.SurfaceBodies.Count;solid_bodies=@($definition.SurfaceBodies|Where-Object IsSolid).Count;mesh_feature_sets=[int]$definition.MeshFeatureSets.Count;planar_sketches=[int]$definition.Sketches.Count;spatial_sketches=[int]$definition.Sketches3D.Count;bom_structure=(Try-Scalar $definition 'BOMStructure')}
        $noSurfaceGeometry=($row.geometry_inventory.surface_bodies -eq 0 -and $row.geometry_inventory.mesh_feature_sets -eq 0)
        if($noSurfaceGeometry){$row.geometry_role='non_surface_reference_geometry'}else{$row.geometry_role='surface_or_mesh_geometry'}
    }
    try{$row.appearance=Get-AppearanceRecord $Document.ActiveAppearance}catch{$row.appearance=@{status='unavailable';error=$_.Exception.Message}}
    try{$material=$Document.ActiveMaterial;if($null -eq $material){throw 'No native material exposed'};$row.material=@{status='native_material';name=[string]$material.Name;display_name=[string]$material.DisplayName}}catch{$row.material=@{status='unavailable';error=$_.Exception.Message}}
    $row.mass_properties=if($noSurfaceGeometry){@{status='not_applicable_no_surface_or_mesh_geometry';note='No mass assigned to construction/reference geometry'}}else{Get-MassRecord $definition}
    if($row.mass_properties.status -eq 'unavailable'){Add-Issue $id $row.mass_properties.error}
    elseif($row.mass_properties.status -eq 'derivado_de_CAD' -and -not $row.mass_properties.tensor_principal_consistency.consistent){Add-Issue $id 'Inertia tensor fails principal-moment invariant consistency'}
    try{$row.bounds_m=@{min=(Point-SI $definition.RangeBox.MinPoint);max=(Point-SI $definition.RangeBox.MaxPoint)}}catch{}
    $row.relations=Get-Relations $definition
    $axes=[Collections.Generic.List[object]]::new()
    try{foreach($axis in $definition.WorkAxes){[void]$axes.Add(@{name=$axis.Name;root_m=(Point-SI $axis.Line.RootPoint);direction=(Vector-Values $axis.Line.Direction)})}}catch{}
    $row.work_axes=$axes.ToArray()
    if($SkipGeometry){
        $row.exports.obj=@{status='not_requested'};$row.exports.step=@{status='not_requested'}
        $row.status='inspected';Write-Inventory;return $id
    }
    if([int]$Document.DocumentType -eq 12290){ # kPartDocumentObject
        $uri='meshes/'+$id+'.obj'
        try{if($noSurfaceGeometry){$row.exports.obj=@{status='not_applicable_no_surface_or_mesh_geometry'}}else{$details=Export-Facets $definition (Join-Path $script:Output $uri);$row.exports.obj=@{uri=$uri;sha256=(Get-FileHash -LiteralPath (Join-Path $script:Output $uri)).Hash.ToLowerInvariant();details=$details;status='exported'}}}
        catch{$row.exports.obj=@{status='failed';error=$_.Exception.Message;stack=$_.ScriptStackTrace};Add-Issue $id $_.Exception.Message}
    } else {$row.exports.obj=@{status='compose_from_occurrences';note='Do not combine movable assembly into one rigid robot link'}}
    $uri='step/'+$id+'.stp'
    try{Export-Step $Document (Join-Path $script:Output $uri);$row.exports.step=@{uri=$uri;sha256=(Get-FileHash -LiteralPath (Join-Path $script:Output $uri)).Hash.ToLowerInvariant();status='exported';units='encoded by STEP translator; inspect FILE_SCHEMA and units'}}
    catch{$row.exports.step=@{status='failed';error=$_.Exception.Message};Add-Issue $id $_.Exception.Message}
    $row.status='inspected'
    Write-Inventory
    return $id
}
function Walk-Occurrences($Definition,[string]$RootId,[string]$ParentId,$ParentMatrix,[int]$Depth=0) {
    if($Depth -gt 64){throw 'Occurrence depth exceeds 64; possible cyclic assembly'}
    for($i=1;$i -le $Definition.Occurrences.Count;$i++){
        $occurrence=$Definition.Occurrences.Item($i)
        $id=$ParentId+'/'+$i.ToString('D4')
        $row=[ordered]@{id=$id;parent_id=$ParentId;root_document_id=$RootId;name=$occurrence.Name;suppressed=$occurrence.Suppressed;visible=$occurrence.Visible;grounded=$occurrence.Grounded;flexible=(Try-Scalar $occurrence 'Flexible');active_model_state=(Try-Scalar $occurrence 'ActiveModelState');rigid_link_assignment='pending'}
        [void]$script:Report.occurrences.Add($row)
        if($occurrence.Suppressed){$row.status='suppressed';continue}
        try{$row.appearance=Get-AppearanceRecord $occurrence.Appearance;$row.appearance.source_type=(Try-Scalar $occurrence 'AppearanceSourceType')}catch{$row.appearance=@{status='unavailable';error=$_.Exception.Message}}
        if($row.flexible){Add-Issue $id 'Flexible subassembly: native document transforms require contextual verification before simulation use'}
        try{
            $local=Convert-MatrixToSI $occurrence.Transformation
            $world=Join-Transforms $ParentMatrix $local
            $row.transform_parent_m=$local; $row.transform_root_m=$world
            $row.matrix_convention='row-major 4x4; column vectors; parent_T_child; translations metres'
            $childDefinition=$occurrence.Definition
            $row.document_id=Register-Document $childDefinition.Document
            $row.status='resolved'
            if($null -eq $row.document_id){$row.status='external_or_unavailable';continue}
            if([int]$childDefinition.Document.DocumentType -eq 12291){Walk-Occurrences $childDefinition $RootId $id $world ($Depth+1)}
        }catch{$row.status='unresolved';$row.error=$_.Exception.Message;Add-Issue $id $_.Exception.Message}
    }
}

if($FunctionsOnly){return}
if($ChordToleranceM -le 0 -or [double]::IsNaN($ChordToleranceM) -or [double]::IsInfinity($ChordToleranceM)){throw 'Chord tolerance must be finite and positive'}
if([Threading.Thread]::CurrentThread.ApartmentState -ne 'STA'){throw 'Run Windows PowerShell with -STA'}
$script:Output=[IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path -LiteralPath $script:Output){throw 'Output exists; choose a fresh evidence directory'}
if(-not $ProbeOnly){
    if(-not $SourceRoot -or -not $Assemblies.Count){throw 'SourceRoot and Assemblies are required'}
    $script:SourcePrefix=(Resolve-Path -LiteralPath $SourceRoot).Path.TrimEnd('\')+'\'
    if($script:Output.StartsWith($script:SourcePrefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Output must be outside source copies'}
}
[void](New-Item -ItemType Directory -Path $script:Output)
[void](New-Item -ItemType Directory -Path (Join-Path $script:Output 'meshes'))
[void](New-Item -ItemType Directory -Path (Join-Path $script:Output 'step'))
[IO.File]::Copy($PSCommandPath,(Join-Path $script:Output 'exporter_source.ps1'))
$script:Report=[ordered]@{
    schema_version='uchuva.inventor_cad_inventory/1';exporter_version='0.2';status='starting';started_utc=[DateTime]::UtcNow.ToString('o')
    exporter_sha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash.ToLowerInvariant()
    source_root=$SourceRoot;requested_assemblies=$Assemblies;chord_tolerance_m=$ChordToleranceM
    units=@{database_length='cm';database_mass='kg';database_angle='rad';output_length='m';output_inertia='kg m^2'}
    documents=[Collections.Generic.List[object]]::new();occurrences=[Collections.Generic.List[object]]::new();roots=[Collections.Generic.List[object]]::new();issues=[Collections.Generic.List[object]]::new();reference_resolution=[Collections.Generic.List[object]]::new()
    limitations=@('CAD properties are not prototype measurements','No robot joints inferred from STEP or assembly constraints','Printed infill, actuator installation and mounting remain unverified','Assembly masses exclude unresolved CAD components; check all reference and occurrence statuses','Inertia direct tensor entries must pass principal-moment invariant consistency')
}
$script:Documents=@{}; $sourceHashes=@{}; $script:GeneratedMembers=@{}; $script:Application=$null; $exitCode=2; $ownedProcess=$null; $resolver=$null
Write-Inventory
try{
    if(@(Get-Process -Name Inventor -ErrorAction SilentlyContinue).Count){throw 'Inventor already running: refusing to attach to or close a user process'}
    if(-not $ProbeOnly){
        $script:SourceFiles=@(Get-ChildItem -LiteralPath $SourceRoot -Recurse -File | Where-Object {$_.Extension -in @('.iam','.ipt','.ipj') -and $_.FullName -notmatch '[\\/]OldVersions[\\/]'})
        foreach($file in $script:SourceFiles){$sourceHashes[$file.FullName]=(Get-FileHash -LiteralPath $file.FullName).Hash}
        if($GeneratedMembersManifest){
            $manifest=Get-Content -LiteralPath $GeneratedMembersManifest -Raw|ConvertFrom-Json
            $script:Report.generated_members_manifest=@{path=[IO.Path]::GetFullPath($GeneratedMembersManifest);sha256=(Get-FileHash -LiteralPath $GeneratedMembersManifest).Hash;identity_policy='Explicit regenerated stock equivalents, never original document identities'}
            foreach($member in $manifest.members){if($member.status -eq 'generated_stock_equivalent'){$script:GeneratedMembers[[string]$member.sha256]=$member}}
        }
    }
    $script:Report.status='creating_private_com_application';Write-Inventory
    $script:Application=New-Object -ComObject Inventor.Application
    $script:Application.Visible=$false
    $script:Application.SilentOperation=$true
    $processes=@(Get-Process -Name Inventor -ErrorAction SilentlyContinue)
    if($processes.Count -ne 1){throw 'Cannot establish exclusive Inventor process ownership'}
    $ownedProcess=$processes[0]
    $script:Report.inventor=@{process_id=$ownedProcess.Id;process_started_utc=$ownedProcess.StartTime.ToUniversalTime().ToString('o');version=$script:Application.SoftwareVersion.DisplayVersion;private_com_instance=$true}
    $script:Report.status='com_application_ready';Write-Inventory
    if($ProbeOnly){$script:Report.status='probe_pass_com_ready_no_cad_opened';$exitCode=0}
    else{
        $interop=Join-Path (Split-Path $ownedProcess.Path -Parent) 'Autodesk.Inventor.Interop.dll'
        $resolverSource=Join-Path $PSScriptRoot 'inventor_reference_resolver.cs'
        [IO.File]::Copy($resolverSource,(Join-Path $script:Output 'inventor_reference_resolver.cs'))
        [void][Reflection.Assembly]::LoadFrom($interop)
        Add-Type -Path $resolverSource -ReferencedAssemblies $interop,'System.Core'
        $script:Report.resolver_sha256=(Get-FileHash -LiteralPath $resolverSource).Hash
        $resolver=[RealHarvesterCad.ReferenceResolver]::new($script:Application,$SourceRoot,[string[]]@($script:SourceFiles|ForEach-Object FullName))
        foreach($assembly in $Assemblies){
            $path=[IO.Path]::GetFullPath((Join-Path $SourceRoot $assembly))
            if(-not(Within-Source $path)){throw 'Requested assembly escapes source root'}
            $options=$script:Application.TransientObjects.CreateNameValueMap()
            $options.Add('SkipAllUnresolvedFiles',$true)
            $options.Add('ExpressModeBehavior','OpenFull')
            $document=$null
            try{
                $script:Report.status='opening_copy';$script:Report.current_source=Source-Relative $path;Write-Inventory
                $document=$script:Application.Documents.OpenWithOptions($path,$options,$false)
                $rootId=Register-Document $document
                [void]$script:Report.roots.Add(@{source_path=(Source-Relative $path);document_id=$rootId})
                if([int]$document.DocumentType -eq 12291){Walk-Occurrences $document.ComponentDefinition $rootId $rootId @(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)}
            }catch{Add-Issue $assembly $_.Exception.Message}
            finally{if($null -ne $document){$document.Close($true)}}
        }
        $script:Report.reference_resolution=@($resolver.Records)
        foreach($record in $resolver.Records){
            if($null -eq $record.selected_file){
                if($record.requested -match '[\\/]AIP[\\/]FEA[\\/]' -and [IO.Path]::GetExtension($record.requested) -in @('.fins','.fsat','.ftes','.fwiz','.fmsh','.fres')){$record.status='excluded_analysis_sidecar_outside_geometry_scope';continue}
                Add-Issue 'unresolved_or_ambiguous_reference' $record.requested;continue
            }
            $loaded=@($script:Report.documents|Where-Object { $_.source_path -eq (Source-Relative $record.selected_file) })
            if($loaded.Count -and $loaded[0].provenance.kind -eq 'GeneratedContentCenter'){$record.status='explicit_generated_standard_equivalent';continue}
            if($record.expected_internal_name -and $loaded.Count -and $loaded[0].internal_name -ne $record.expected_internal_name){
                if($loaded[0].provenance.kind -eq 'GeneratedContentCenter'){$record.status='explicit_generated_standard_equivalent_identity_differs'}
                else{Add-Issue 'reference_identity_mismatch' $record.selected_file}
            }
        }
        if($script:Report.issues.Count -eq 0 -and $script:Report.roots.Count -eq $Assemblies.Count){$script:Report.status='exported_cad_not_hardware_validated';$exitCode=0}else{$script:Report.status='partial_export'}
    }
}catch{$script:Report.status='blocked';Add-Issue 'COM_or_export' $_.Exception.Message}
finally{
    if($null -ne $resolver){$script:Report.reference_resolution=@($resolver.Records);$resolver.Dispose()}
    if($null -ne $script:Application -and $null -ne $ownedProcess){
        try{for($i=$script:Application.Documents.Count;$i -ge 1;$i--){$script:Application.Documents.Item($i).Close($true)};$script:Application.Quit()}catch{Add-Issue 'private_application_cleanup' $_.Exception.Message}
    }
    $changed=@()
    foreach($path in $sourceHashes.Keys){if(-not(Test-Path -LiteralPath $path) -or (Get-FileHash -LiteralPath $path).Hash -ne $sourceHashes[$path]){$changed+=$path}}
    $script:Report.source_integrity=@{files_hashed=$sourceHashes.Count;unchanged=($changed.Count -eq 0);changed_files=$changed;sha256_by_path=$sourceHashes}
    if($changed.Count){$script:Report.status='source_integrity_failed';$exitCode=3}
    $script:Report.finished_utc=[DateTime]::UtcNow.ToString('o');Write-Inventory
}
Write-Output ('CAD inventory: '+(Join-Path $script:Output 'cad_inventory.json'))
exit $exitCode
