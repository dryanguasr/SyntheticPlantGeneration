// Original project code. Compiles against the installed Inventor interop only.
using System;
using System.Collections.Generic;
using System.IO;
using Inventor;
using Path = System.IO.Path;
using File = System.IO.File;

namespace RealHarvesterCad {
    public sealed class ResolutionRecord {
        public string requested;
        public string referencing_document;
        public string expected_internal_name;
        public string selected_file;
        public string status;
    }
    public sealed class ReferenceResolver : IDisposable {
        private readonly FileAccessEvents events;
        private readonly string root;
        private readonly HashSet<string> owned;
        private readonly Dictionary<string,List<string>> names;
        public readonly List<ResolutionRecord> Records = new List<ResolutionRecord>();

        public ReferenceResolver(object application, string sourceRoot, string[] files) {
            root=Path.GetFullPath(sourceRoot).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
            owned=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            names=new Dictionary<string,List<string>>(StringComparer.OrdinalIgnoreCase);
            foreach(string file in files) {
                string full=Path.GetFullPath(file);
                if(!full.StartsWith(root,StringComparison.OrdinalIgnoreCase))throw new ArgumentException("Reference escapes source root");
                owned.Add(full);
                string name=Path.GetFileName(full);
                if(!names.ContainsKey(name))names[name]=new List<string>();
                names[name].Add(full);
            }
            events=((Inventor.Application)application).FileAccessEvents;
            events.OnFileResolution+=Resolve;
        }
        private static string ContextValue(NameValueMap context,string key) {
            try{return Convert.ToString(context.Value[key]);}catch{return null;}
        }
        private string OwnedCandidate(string path) {
            try {
                string full=Path.GetFullPath(path);
                return owned.Contains(full) && File.Exists(full) ? full : null;
            }catch{return null;}
        }
        private void Resolve(string relative,string library,ref byte[] logical,
                EventTimingEnum timing,NameValueMap context,out string fullName,out HandlingCodeEnum handled) {
            fullName="";handled=HandlingCodeEnum.kEventNotHandled;
            if(timing!=EventTimingEnum.kBefore)return;
            ResolutionRecord row=new ResolutionRecord();
            row.requested=relative;
            row.referencing_document=ContextValue(context,"DirectReferencingFileName");
            row.expected_internal_name=ContextValue(context,"InternalName");
            string selected=OwnedCandidate(relative);
            if(selected==null && row.referencing_document!=null) {
                selected=OwnedCandidate(Path.Combine(Path.GetDirectoryName(row.referencing_document),relative));
            }
            if(selected==null)selected=OwnedCandidate(Path.Combine(root,relative));
            List<string> matches;
            if(selected==null && names.TryGetValue(Path.GetFileName(relative),out matches) && matches.Count==1)selected=matches[0];
            row.selected_file=selected;
            if(selected!=null) {
                fullName=selected;handled=HandlingCodeEnum.kEventHandled;
                row.status="resolved_to_downloaded_copy_identity_pending";
            } else {
                // No fallback to unrelated absolute files or OldVersions.
                fullName=Path.Combine(root,"__unresolved_reference__",Path.GetFileName(relative));
                handled=HandlingCodeEnum.kEventHandled;
                row.status="missing_or_ambiguous_owned_copy";
            }
            Records.Add(row);
        }
        public void Dispose(){events.OnFileResolution-=Resolve;}
    }
}
