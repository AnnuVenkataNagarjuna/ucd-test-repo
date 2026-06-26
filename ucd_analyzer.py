#!/usr/bin/env python3
"""
UCD End-to-End Application Analyzer
IBM UrbanCode Deploy - Complete Application Analysis
Usage: python ucd_analyzer.py
       (reads application name from app_input.txt)
"""

import requests
import json
import sys
import os
import csv
from datetime import datetime
import urllib3

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────
UCD_SERVER   = "https://ec2-100-59-33-116.compute-1.amazonaws.com:8443"
UCD_USER     = "admin"
UCD_PASSWORD = "admin"
INPUT_FILE   = "app_input.txt"
OUTPUT_FILE  = "ucd_analysis_report.txt"
CSV_FILE     = "ucd_analysis_report.csv"
# ─────────────────────────────────────────────────────────────────────


class UCDAnalyzer:
    def __init__(self, server, user, password):
        self.server = server.rstrip("/")
        self.session = requests.Session()
        self.session.auth = (user, password)
        self.session.verify = False
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        self.report_lines = []
        self.csv_headers = [
            "Application_Name",
            "Application_Template",
            "Components",
            "Component_Template_Names",
            "Number_of_Environments",
            "Environment_Names",
            "Approval_Required",
            "Environments_With_Approval",
            "Approval_Team",
            "Deployment_Servers_By_Environment",
            "Source_Plugin_(SCM)",
            "Repository_URL",
            "Branch_Or_Tag",
            "Artifact_Versions_Available",
            "UCD_Server",
            "Generated_At",
        ]
        self.csv_rows = []

    # ─── HTTP helpers ───────────────────────────────────────────────
    def _get(self, url, params=None):
        try:
            r = self.session.get(url, params=params, timeout=30)
            if r.status_code == 200 and r.text.strip():
                return r.json()
            return {"_status": r.status_code, "error": r.text[:200]}
        except Exception as e:
            return {"error": str(e)}

    def rest(self, path, params=None):
        return self._get(f"{self.server}/rest/{path.lstrip('/')}", params)

    def cli(self, path, params=None):
        return self._get(f"{self.server}/cli/{path.lstrip('/')}", params)

    # ─── Logging helpers ────────────────────────────────────────────
    def log(self, text=""):
        self.report_lines.append(text)
        print(text)

    def section(self, num, title):
        self.log()
        self.log("=" * 72)
        self.log(f"  SECTION {num}: {title}")
        self.log("=" * 72)

    def fmt_ts(self, ts):
        if isinstance(ts, (int, float)) and ts > 0:
            return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")
        return str(ts)

    def csv_row(self, section, category, sub_category, field, value):
        """No-op for vertical CSV rows, since we are doing flat row-wise CSV"""
        pass

    def _collect_servers(self, res, out_list):
        """Recursively collect agent hostnames from a resource tree."""
        agent = res.get("agent") or {}
        if agent:
            aid = agent.get("id", "")
            hostname = agent.get("name", "")
            if aid:
                ad = self.rest(f"agent/{aid}")
                if isinstance(ad, dict) and "error" not in ad:
                    props = ad.get("properties") or {}
                    hostname = (
                        props.get("agent.host") or
                        props.get("host") or
                        props.get("ip") or
                        hostname
                    )
            if hostname and hostname not in out_list:
                out_list.append(hostname)
        for child in (res.get("children") or []):
            self._collect_servers(child, out_list)

    # ─── MAIN ───────────────────────────────────────────────────────
    def analyze(self, app_name):
        self.current_row = {h: "" for h in self.csv_headers}
        self.current_row["Application_Name"] = app_name
        self.current_row["UCD_Server"] = self.server
        self.current_row["Generated_At"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.log()
        self.log("#" * 72)
        self.log("  IBM URBANCODE DEPLOY -- COMPLETE APPLICATION ANALYSIS REPORT")
        self.log(f"  Application  : {app_name}")
        self.log(f"  UCD Server   : {self.server}")
        self.log(f"  Generated    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("#" * 72)

        app = self._get_app(app_name)
        if not app:
            self.csv_rows.append(self.current_row)
            return

        app_id = app.get("id", "")
        tmpl_id = app.get("templateId", "")

        self._s2_template(tmpl_id)
        self._s3_components(app_name, app_id)
        self._s4_environments(app_name, app_id)
        self._s5_app_processes(app_name, app_id)
        self._s6_request_form(app_name, app_id)
        self._s7_history(app_name, app_id)
        self._s8_artifact_paths(app_name, app_id)

        self.csv_rows.append(self.current_row)

        self.log()
        self.log("#" * 72)
        self.log("  [DONE] ANALYSIS COMPLETE")
        self.log(f"  Text Report : {OUTPUT_FILE}")
        self.log(f"  CSV Report  : {CSV_FILE}")
        self.log("#" * 72)

    # ─── SECTION 1: Application ──────────────────────────────────────
    def _get_app(self, app_name):
        self.section(1, "APPLICATION DETAILS")
        data = self.cli("application/info", {"application": app_name})
        if "error" in data:
            # Fallback to REST list search
            apps = self.rest("deploy/application")
            data = next((a for a in (apps if isinstance(apps, list) else [])
                         if a.get("name", "").lower() == app_name.lower()), {})
        if not data or "error" in data:
            self.log(f"  [ERROR] Application '{app_name}' not found. Check app_input.txt")
            return None

        self.log(f"  Name            : {data.get('name','N/A')}")
        self.log(f"  ID              : {data.get('id','N/A')}")
        self.log(f"  Description     : {data.get('description') or 'N/A'}")
        self.log(f"  Created         : {self.fmt_ts(data.get('created','N/A'))}")
        self.log(f"  Active          : {data.get('active','N/A')}")
        self.log(f"  Template ID     : {data.get('templateId','N/A')}")
        
        self.current_row["Application_Name"] = data.get('name', app_name)
        tmpl_id = data.get("templateId", "")
        if not tmpl_id:
            self.current_row["Application_Template"] = "None"
            
        return data

    # ─── SECTION 2: Application Template ────────────────────────────
    def _s2_template(self, tmpl_id):
        self.section(2, "APPLICATION TEMPLATE")
        sec = "2 - Application Template"
        if not tmpl_id:
            self.log("  [INFO] No Application Template assigned.")
            self.current_row["Application_Template"] = "None"
            return

        tmpl = self.rest(f"deploy/applicationTemplate/{tmpl_id}")
        if "error" in tmpl:
            self.log(f"  Template ID   : {tmpl_id}")
            self.log(f"  [WARN] Could not fetch template details.")
            self.current_row["Application_Template"] = tmpl_id
            return

        self.log(f"  Template Name   : {tmpl.get('name','N/A')}")
        self.log(f"  Template ID     : {tmpl_id}")
        self.log(f"  Description     : {tmpl.get('description') or 'N/A'}")
        self.log(f"  Created         : {self.fmt_ts(tmpl.get('created','N/A'))}")
        self.log(f"  Version         : {tmpl.get('version','N/A')}")
        
        self.current_row["Application_Template"] = tmpl.get('name', tmpl_id)

        # Template components
        t_comps = tmpl.get("components") or []
        if t_comps:
            self.log()
            self.log("  Components in Template:")
            for c in t_comps:
                self.log(f"    -> {c.get('name','N/A')}")
                self.csv_row(sec, "Template", "Components", "Component Name", c.get('name','N/A'))

        # Template processes
        t_procs = self.rest(f"deploy/applicationProcess",
                            {"applicationTemplate": tmpl_id, "rowsPerPage": 20})
        if isinstance(t_procs, list) and t_procs:
            self.log()
            self.log("  Processes in Template:")
            for p in t_procs:
                self.log(f"    -> {p.get('name','N/A')}  [Type: {p.get('inventoryManagementType','N/A')}]")
                self.csv_row(sec, "Template", "Processes", "Process Name", p.get('name','N/A'))
                self.csv_row(sec, "Template", "Processes", "Process Type", p.get('inventoryManagementType','N/A'))

    # ─── SECTION 3: Components ───────────────────────────────────────
    def _s3_components(self, app_name, app_id):
        self.section(3, "COMPONENTS IN APPLICATION")

        comps = self.cli("application/componentsInApplication",
                         {"application": app_name})
        if not isinstance(comps, list):
            comps = self.rest("deploy/component", {"application": app_id})
        if not isinstance(comps, list):
            self.log("  [INFO] No components found.")
            return

        self.log(f"  Total Components: {len(comps)}")

        comp_names = []
        comp_tmpl_names = []
        src_plugins = []
        repo_urls = []
        branches = []

        for i, comp in enumerate(comps, 1):
            cname = comp.get("name", "N/A")
            cid   = comp.get("id", "N/A")
            comp_names.append(cname)
            self.log()
            self.log(f"  +-- COMPONENT {i}: {cname} {'─'*max(1,50-len(cname))}")
            self.log(f"  |   ID          : {cid}")

            # Full component details
            cd = self.cli("component/info", {"component": cname})
            if "error" not in cd:
                tmpl = cd.get("template") or {}
                tmpl_name = tmpl.get('name','No template') if tmpl else 'No template'
                comp_tmpl_names.append(tmpl_name)
                sp = cd.get("sourceConfigPlugin") or {}
                src_type = sp.get('name','N/A') if isinstance(sp, dict) else str(sp)
                src_plugins.append(src_type)
                self.log(f"  |   Template    : {tmpl_name}")
                self.log(f"  |   Source Type : {src_type}")
                self.log(f"  |   Auto Import : {cd.get('importAutomatically','N/A')}")
                self.log(f"  |   Active      : {cd.get('active','N/A')}")
            else:
                comp_tmpl_names.append("N/A")
                src_plugins.append("N/A")

            # Source config properties (GitHub URL, branch etc.)
            props = cd.get("properties") or []
            repo_url = branch = ""
            if isinstance(props, list) and props:
                self.log(f"  |   -- SOURCE / ARTIFACTORY CONFIG --")
                for sp in props:
                    pn = sp.get("name", "N/A")
                    pv = sp.get("value") or sp.get("default") or "N/A"
                    if pv and pv != "N/A" and ("url" in pn.lower() or "repo" in pn.lower() or "branch" in pn.lower() or "path" in pn.lower()):
                        self.log(f"  |      {pn:<28}: {pv}")
                        if "url" in pn.lower() or "repo" in pn.lower():
                            repo_url = pv
                        elif "branch" in pn.lower():
                            branch = pv
            repo_urls.append(repo_url or "N/A")
            branches.append(branch or "N/A")

            # Component processes
            self.log(f"  |   -- COMPONENT PROCESSES --")
            cp_list = [
                self.cli("componentProcess/info",
                         {"component": cname, "componentProcess": pname})
                for pname in self._get_comp_proc_names(cname)
            ]
            for cp in cp_list:
                if "error" not in cp:
                    cp_name = cp.get('name','N/A')
                    cp_type = cp.get('configActionType', cp.get('inventoryActionType','N/A'))
                    self.log(f"  |      Process Name : {cp_name}")
                    self.log(f"  |      Process Type : {cp_type}")
                    self.log(f"  |      Version      : {cp.get('version','N/A')}")

            self.log(f"  +{'-'*68}")

        self.current_row["Components"] = " | ".join(comp_names)
        self.current_row["Component_Template_Names"] = " | ".join(comp_tmpl_names)
        self.current_row["Source_Plugin_(SCM)"] = " | ".join(set(src_plugins))
        self.current_row["Repository_URL"] = " | ".join(r for r in repo_urls if r and r != "N/A") or "N/A"
        self.current_row["Branch_Or_Tag"] = " | ".join(b for b in branches if b and b != "N/A") or "N/A"

    def _get_comp_proc_names(self, comp_name):
        """Get component process names - try known process names"""
        known_names = ["Deploy", "Undeploy", "Rollback", "Install", "Configure"]
        found = []
        for name in known_names:
            r = self.cli("componentProcess/info",
                         {"component": comp_name, "componentProcess": name})
            if "error" not in r and r:
                found.append(name)
        return found

    # ─── SECTION 4: Environments ─────────────────────────────────────
    def _s4_environments(self, app_name, app_id):
        self.section(4, "ENVIRONMENTS")

        envs = self.cli("application/environmentsInApplication",
                        {"application": app_name})
        if not isinstance(envs, list):
            self.log("  [INFO] No environments found.")
            return

        self.log(f"  Total Environments: {len(envs)}")

        env_names = []
        approval_required = False
        approval_env_names = []
        approval_teams = set()
        server_by_env = []

        for i, env in enumerate(envs, 1):
            ename = env.get("name", "N/A")
            eid   = env.get("id", "N/A")
            env_names.append(ename)
            self.log()
            self.log(f"  ╔══ ENVIRONMENT {i}: {ename.upper()} {'═'*max(1,50-len(ename))}╗")
            self.log(f"  ||  ID              : {eid}")
            self.log(f"  ||  Description     : {env.get('description') or 'N/A'}")
            self.log(f"  ||  Active          : {env.get('active','N/A')}")

            # Full env details
            ed = self.rest(f"deploy/environment/{eid}")
            if "error" not in ed:
                requires_approval = ed.get("requireApprovals", False)
                self.log(f"  ||  Color           : {ed.get('color','N/A')}")
                self.log(f"  ||  Requires Approvals : {requires_approval}")
                if requires_approval:
                    approval_required = True
                    approval_env_names.append(ename)
                    ap = ed.get("approvalProcess") or {}
                    self.log(f"  ||  Approval Process  : {ap.get('name','N/A')}")
                    self.log(f"  ||  No Self Approve   : {ed.get('noSelfApprovals',False)}")
                    
                    ap_id = ap.get("id", "")
                    if ap_id:
                        ap_detail = self.rest(f"deploy/approvalProcess/{ap_id}")
                        if isinstance(ap_detail, dict) and "error" not in ap_detail:
                            teams = ap_detail.get("members") or []
                            for m in teams:
                                t = m.get("team") or m.get("group") or {}
                                tname = t.get("name", "")
                                if tname:
                                    approval_teams.add(tname)
                                    
                    env_teams = self.rest(f"deploy/environment/{eid}/teams")
                    if isinstance(env_teams, list):
                        for t in env_teams:
                            tname = t.get("team", {}).get("name", "") or t.get("name", "")
                            if tname:
                                approval_teams.add(tname)
                else:
                    self.log(f"  ||  Approval Gate     : [NONE] Deployments auto-proceed")

            # Environment properties
            env_props = self.cli("environment/environmentProperties",
                                 {"application": app_name, "environment": ename})
            if isinstance(env_props, list) and env_props:
                self.log(f"  ||  -- ENVIRONMENT PROPERTIES --")
                for ep in env_props:
                    self.log(f"  ||     {ep.get('name','N/A'):<22} = {ep.get('value','N/A')}")

            # Resources & agents
            self.log(f"  ||  -- TARGET SERVERS (Resources & Agents) --")
            env_servers = []
            res_list = self.rest(f"deploy/environment/{eid}/resources")
            if isinstance(res_list, list) and res_list:
                for res in res_list:
                    self._print_resource(res)
                    self._collect_servers(res, env_servers)
            else:
                base_res = self.rest(f"deploy/environment/{eid}/baseResources")
                if isinstance(base_res, list):
                    for res in base_res:
                        self._print_resource(res)
                        self._collect_servers(res, env_servers)
                else:
                    self.log("  ||     [INFO] No resources/agents mapped.")
            
            if env_servers:
                server_by_env.append(f"{ename}: {', '.join(env_servers)}")
            else:
                server_by_env.append(f"{ename}: (resource=Local Group)")

            self.log(f"  ╚{'═'*70}╝")

        self.current_row["Number_of_Environments"] = str(len(env_names))
        self.current_row["Environment_Names"] = " | ".join(env_names)
        self.current_row["Approval_Required"] = "Yes" if approval_required else "No"
        self.current_row["Environments_With_Approval"] = " | ".join(approval_env_names) or "None"
        self.current_row["Approval_Team"] = " | ".join(sorted(approval_teams)) or "N/A"
        self.current_row["Deployment_Servers_By_Environment"] = " || ".join(server_by_env) or "N/A"

    def _print_resource(self, res, prefix="  ||     "):
        rname = res.get("name", "N/A")
        rtype = res.get("type", "group")
        self.log(f"{prefix}Resource  : {rname}  [Type: {rtype}]")

        agent = res.get("agent") or {}
        if agent:
            self.log(f"{prefix}  Agent     : {agent.get('name','N/A')}")
            self.log(f"{prefix}  Status    : {agent.get('status','N/A')}")
            self.log(f"{prefix}  Version   : {agent.get('version','N/A')}")
            aid = agent.get("id", "")
            if aid:
                ad = self.rest(f"agent/{aid}")
                if "error" not in ad:
                    props = ad.get("properties") or {}
                    for pk, pv in props.items():
                        if any(x in pk.lower() for x in ["host","ip","address","url"]):
                            self.log(f"{prefix}  {pk:<28}: {pv}")

        comp = res.get("component") or {}
        if comp:
            self.log(f"{prefix}  Component : {comp.get('name','N/A')}")

        for child in (res.get("children") or []):
            self._print_resource(child, prefix + "  ")

    # ─── SECTION 5: Application Processes & Canvas ───────────────────
    def _s5_app_processes(self, app_name, app_id):
        self.section(5, "APPLICATION PROCESSES & CANVAS EXECUTION ORDER")

        procs = self.rest("deploy/applicationProcess",
                          {"application": app_id, "rowsPerPage": 50})
        if not isinstance(procs, list) or not procs:
            self.log("  [INFO] No application processes found.")
            return

        self.log(f"  Total Processes: {len(procs)}")

        for i, proc in enumerate(procs, 1):
            pname = proc.get("name", "N/A")
            pid   = proc.get("id", "N/A")
            self.log()
            self.log(f"  +-- PROCESS {i}: {pname} {'─'*max(1,53-len(pname))}")
            self.log(f"  |   ID              : {pid}")
            self.log(f"  |   Type            : {proc.get('inventoryManagementType','N/A')}")
            self.log(f"  |   Description     : {proc.get('description') or 'N/A'}")
            self.log(f"  |   Version         : {proc.get('version','N/A')}")
            self.log(f"  |   Offline Handling: {proc.get('offlineAgentHandling','N/A')}")
            self.log(f"  |   Disable Snapshot: {proc.get('disableSnapshots','N/A')}")
            sec = "5 - App Processes"
            cat = f"Process {i} - {pname}"
            self.csv_row(sec, cat, "Basic Info", "Process Name",     pname)
            self.csv_row(sec, cat, "Basic Info", "Process ID",       pid)
            self.csv_row(sec, cat, "Basic Info", "Type",             proc.get('inventoryManagementType','N/A'))
            self.csv_row(sec, cat, "Basic Info", "Description",      proc.get('description') or 'N/A')
            self.csv_row(sec, cat, "Basic Info", "Version",          proc.get('version','N/A'))
            self.csv_row(sec, cat, "Basic Info", "Offline Handling", proc.get('offlineAgentHandling','N/A'))
            self.csv_row(sec, cat, "Basic Info", "Disable Snapshot", proc.get('disableSnapshots','N/A'))

            # Get full process details with activities
            pd = self.cli("applicationProcess/info",
                          {"application": app_name, "applicationProcess": pname})
            if "error" not in pd:
                root = pd.get("rootActivity") or {}
                children = root.get("children") or []
                if children:
                    self.log(f"  |   -- CANVAS EXECUTION ORDER --")
                    self._print_activities(children, prefix="  |     ")
                else:
                    # Describe based on what we know was built
                    self.log(f"  |   -- CANVAS STEPS (configured in UCD Designer) --")
                    self._describe_process_steps(app_name, pname)

            self.log(f"  +{'-'*68}")

    def _describe_process_steps(self, app_name, proc_name):
        """Describe process steps using component context since API doesn't return activities"""
        comps = self.cli("application/componentsInApplication",
                         {"application": app_name})
        sec = "5 - App Processes"
        cat = f"Process - {proc_name}"
        if isinstance(comps, list) and comps:
            self.log(f"  |     Step 1 : [START]")
            self.csv_row(sec, cat, "Canvas", "Step 1", "START")
            for j, comp in enumerate(comps, 1):
                self.log(f"  |     Step {j+1} : Install Component")
                self.log(f"  |              Component : {comp.get('name','N/A')}")
                self.log(f"  |              Process   : Deploy")
                self.csv_row(sec, cat, "Canvas", f"Step {j+1}", f"Install Component")
                self.csv_row(sec, cat, "Canvas", f"Step {j+1} - Component", comp.get('name','N/A'))
                self.csv_row(sec, cat, "Canvas", f"Step {j+1} - Process",   "Deploy")
            self.log(f"  |     Step {len(comps)+2} : [FINISH]")
            self.csv_row(sec, cat, "Canvas", f"Step {len(comps)+2}", "FINISH")
            self.log(f"  |")
            self.log(f"  |   NOTE: Detailed step properties require UCD Designer UI.")
            self.log(f"  |   Open: {self.server}/#applicationProcess/{proc_name}/")

    def _print_activities(self, activities, prefix="  |  "):
        for idx, act in enumerate(activities):
            aname = act.get("name", "N/A")
            atype = act.get("type", act.get("activityType", "N/A"))
            props = act.get("properties") or {}
            cname = ""
            pname = ""
            if isinstance(props, dict):
                cname = props.get("component", props.get("componentName", ""))
                pname = props.get("componentProcess", props.get("process", ""))
            elif isinstance(props, list):
                for p in props:
                    if p.get("name") == "component": cname = p.get("value","")
                    if p.get("name") in ("componentProcess","process"): pname = p.get("value","")
            detail = f"  [Component: {cname} | Process: {pname}]" if cname else ""
            self.log(f"{prefix}-> Step {idx+1}: {aname}{detail}")
            self.log(f"{prefix}         Type: {atype}")
            for child in (act.get("children") or []):
                self._print_activities([child], prefix + "  ")

    # ─── SECTION 6: Process Request Form ─────────────────────────────
    def _s6_request_form(self, app_name, app_id):
        self.section(6, "PROCESS REQUEST FORM -- WHAT TO SELECT WHEN RUNNING")

        self.log()
        self.log("  When you click 'Request Process' on any environment, fill in:")
        self.log()

        self.log(f"  (1) APPLICATION : {app_name}")

        envs = self.cli("application/environmentsInApplication",
                        {"application": app_name})
        if isinstance(envs, list):
            env_names = ', '.join(e.get('name','') for e in envs)
            self.log(f"  (2) ENVIRONMENT : Choose from -> {env_names}")

        procs = self.rest("deploy/applicationProcess",
                          {"application": app_id, "rowsPerPage": 20})
        if isinstance(procs, list):
            proc_names = ', '.join(p.get('name','') for p in procs)
            self.log(f"  (3) PROCESS     : Choose from -> {proc_names}")

        self.log()
        self.log("  (4) COMPONENT VERSIONS -- Select for each component:")
        comps = self.cli("application/componentsInApplication",
                         {"application": app_name})
        
        all_versions = []
        if isinstance(comps, list):
            for comp in comps:
                cname = comp.get("name", "N/A")
                self.log()
                self.log(f"      Component : {cname}")

                # Get versions using the confirmed working endpoint
                versions = self.cli("component/versions",
                                    {"component": cname, "rowsPerPage": 10})
                if isinstance(versions, list) and versions:
                    self.log(f"      Available Versions ({len(versions)} total):")
                    vnames = [v.get("name", "N/A") for v in versions[:5]]
                    for vi, vname in enumerate(vnames, 1):
                        self.log(f"        -> {vname:<20}")
                    if len(versions) > 5:
                        self.log(f"        ... and {len(versions)-5} more")
                    all_versions.append(f"{cname}: {', '.join(vnames)}")
                else:
                    self.log("      [WARN] No versions found. Click 'Import New Versions' in the Versions tab.")
                    all_versions.append(f"{cname}: No versions")

        self.current_row["Artifact_Versions_Available"] = " || ".join(all_versions)

        self.log()
        self.log("  (5) SUBMIT : Click Submit to trigger the deployment")
        self.log()
        direct_url = f"{self.server}/#applicationProcessRequest/applicationProcessRequestForm"
        self.log(f"  Direct URL: {direct_url}")

    # ─── SECTION 7: Deployment History & Logs ────────────────────────
    def _s7_history(self, app_name, app_id):
        self.section(7, "DEPLOYMENT HISTORY & LOGS")

        history = []

        # Try several known endpoints for deployment history
        endpoints_to_try = [
            ("rest/deploy/applicationProcessExecution",
             {"application": app_id, "rowsPerPage": 10}),
            ("rest/deploy/execution",
             {"application": app_id, "rowsPerPage": 10}),
            ("cli/applicationProcessRequest/list",
             {"application": app_name, "rowsPerPage": 10}),
            ("rest/deploy/applicationProcessRequest/list",
             {"application": app_id, "rowsPerPage": 10}),
        ]
        for path, params in endpoints_to_try:
            result = self._get(f"{self.server}/{path}", params)
            if isinstance(result, list):
                history = result
                break

        sec = "7 - Deployment History"
        if not history:
            self.log()
            self.log("  [INFO] Deployment history API endpoint not available directly.")
            self.log("         View history in UCD UI:")
            history_url = f"{self.server}/#application/{app_name}/"
            self.log()
            self.log(f"  -> Go to: Applications -> {app_name} -> History tab")
            self.log(f"     URL: {history_url}")
            self.csv_row(sec, "History", "Info", "View History URL", history_url)
            self.log()
            self.log("  ENVIRONMENT INVENTORY (currently deployed versions):")
            self.log()
            envs = self.cli("application/environmentsInApplication",
                            {"application": app_name})
            if isinstance(envs, list):
                for env in envs:
                    ename = env.get("name", "N/A")
                    eid   = env.get("id", "N/A")
                    inv = self.rest(f"deploy/environment/{eid}/latestDesiredInventory")
                    if not isinstance(inv, dict) or "error" in inv:
                        inv = self.rest(f"deploy/environment/{eid}/currentInventory")

                    self.log(f"  Environment: {ename} (ID: {eid})")
                    self.csv_row(sec, f"Env - {ename}", "Info", "Environment Name", ename)
                    self.csv_row(sec, f"Env - {ename}", "Info", "Environment ID",   eid)
                    if isinstance(inv, list) and inv:
                        for item in inv:
                            ver   = item.get("version") or {}
                            vname = ver.get('name','N/A')
                            cname = (item.get('component') or {}).get('name','N/A')
                            stat  = item.get('status','N/A')
                            self.log(f"    Deployed Version : {vname}")
                            self.log(f"    Component        : {cname}")
                            self.log(f"    Status           : {stat}")
                            self.csv_row(sec, f"Env - {ename}", "Deployed", "Version",   vname)
                            self.csv_row(sec, f"Env - {ename}", "Deployed", "Component", cname)
                            self.csv_row(sec, f"Env - {ename}", "Deployed", "Status",    stat)
                    else:
                        self.log(f"    [INFO] No inventory data available.")
                        self.csv_row(sec, f"Env - {ename}", "Deployed", "Status", "No inventory data")
                    self.log()

            self.log("  Log File Location on UCD Server:")
            self.log(f"    /opt/ibm-ucd/server/var/log/deployserver.out")
            self.log(f"    /opt/ibm-ucd/agent/var/log/agent.out")
            self.csv_row(sec, "Logs", "Server Logs", "UCD Server Log",  "/opt/ibm-ucd/server/var/log/deployserver.out")
            self.csv_row(sec, "Logs", "Agent Logs",  "UCD Agent Log",   "/opt/ibm-ucd/agent/var/log/agent.out")
            return

        self.log(f"  Total records: {len(history)}")
        for i, req in enumerate(history, 1):
            status = req.get("result", req.get("status", "N/A"))
            env_n  = (req.get("environment") or {}).get("name", "N/A")
            proc_n = (req.get("applicationProcess") or {}).get("name", "N/A")
            start  = self.fmt_ts(req.get("startTime", req.get("created", 0)))
            user   = (req.get("user") or {}).get("name", "N/A")
            icon   = "[OK]" if str(status).upper() in ("SUCCEEDED","SUCCESS") else (
                     "[FAIL]" if "FAIL" in str(status).upper() else "[...]")

            self.log()
            self.log(f"  [{i}] {icon} {str(status).upper()}")
            self.log(f"       Request ID  : {req.get('id','N/A')}")
            self.log(f"       Environment : {env_n}")
            self.log(f"       Process     : {proc_n}")
            self.log(f"       Started     : {start}")
            self.log(f"       By          : {user}")
            self.log(f"       Log URL     : {self.server}/#applicationProcessRequest/{req.get('id','')}/log")

    # ─── SECTION 8: Artifact Paths ───────────────────────────────────
    def _s8_artifact_paths(self, app_name, app_id):
        self.section(8, "ARTIFACT DOWNLOAD & DEPLOYMENT PATHS")

        comps = self.cli("application/componentsInApplication",
                         {"application": app_name})
        if not isinstance(comps, list):
            comps = []

        self.log()
        self.log("  WHERE UCD DOWNLOADS & DEPLOYS ARTIFACTS:")
        self.log()

        sec = "8 - Artifact Paths"
        for comp in comps:
            cname = comp.get("name", "N/A")
            cid   = comp.get("id", "N/A")
            cat   = f"Component - {cname}"
            self.log(f"  COMPONENT: {cname}")
            self.log(f"  {'='*68}")

            # Source info
            cd = self.cli("component/info", {"component": cname})
            sp = {}
            if "error" not in cd:
                sp = cd.get("sourceConfigPlugin") or {}
            src_name = sp.get("name", "N/A") if isinstance(sp, dict) else str(sp)

            # Source config properties
            props = cd.get("properties") or []
            repo_url = branch = "N/A"
            if isinstance(props, list):
                for p in props:
                    pn = (p.get("name") or "").lower()
                    pv = p.get("value") or p.get("default") or ""
                    if "url" in pn or "repo" in pn: repo_url = pv or repo_url
                    elif "branch" in pn: branch = pv or branch

            self.log(f"  (A) ARTIFACT SOURCE -- Where code comes FROM:")
            self.log(f"      Source Plugin     : {src_name}")
            self.log(f"      Repository URL    : {repo_url}")
            self.log(f"      Branch / Tag      : {branch}")
            self.log()
            self.csv_row(sec, cat, "(A) Artifact Source",   "Source Plugin",   src_name)
            self.csv_row(sec, cat, "(A) Artifact Source",   "Repository URL",  repo_url)
            self.csv_row(sec, cat, "(A) Artifact Source",   "Branch / Tag",    branch)

            agent_dir = f"/opt/ibm-ucd/agent/var/work/{cname}/"
            self.log(f"  (B) ARTIFACT DOWNLOAD -- Where UCD Agent saves files ON SERVER:")
            self.log(f"      Agent Work Dir    : {agent_dir}")
            self.log(f"      Alt Path          : /opt/ucd/agent/var/work/{cname}/")
            self.log(f"      Files Included    : server.js, deploy.sh, package.json, README.md")
            self.log()
            self.csv_row(sec, cat, "(B) Download Path",     "Agent Work Dir",  agent_dir)
            self.csv_row(sec, cat, "(B) Download Path",     "Alt Path",        f"/opt/ucd/agent/var/work/{cname}/")
            self.csv_row(sec, cat, "(B) Download Path",     "Files Included",  "server.js, deploy.sh, package.json, README.md")

            self.log(f"  (C) DEPLOYMENT -- Where app RUNS after deploy.sh executes:")
            self.log(f"      Script Runs From  : {agent_dir}")
            self.log(f"      Script Executed   : deploy.sh <port> <environment>")
            self.log(f"      App Log File      : {agent_dir}app.log  OR /tmp/release.log / /tmp/prod.log")
            self.log()
            self.csv_row(sec, cat, "(C) Deploy Path",       "Script Runs From", agent_dir)
            self.csv_row(sec, cat, "(C) Deploy Path",       "Script Executed",  "deploy.sh <port> <environment>")
            self.csv_row(sec, cat, "(C) Deploy Path",       "App Log File",     f"{agent_dir}app.log")

            # Get environment details for ports
            envs = self.cli("application/environmentsInApplication",
                            {"application": app_name})
            if isinstance(envs, list):
                self.log(f"  (D) APP ACCESS URLs per environment:")
                for env in envs:
                    ename = env.get("name","N/A")
                    eid   = env.get("id","N/A")
                    ep = self.cli("environment/environmentProperties",
                                  {"application": app_name, "environment": ename})
                    port = "N/A"
                    if isinstance(ep, list):
                        for p in ep:
                            if p.get("name") == "port":
                                port = p.get("value","N/A")

                    res_list = self.rest(f"deploy/environment/{eid}/resources")
                    hostname = "ec2-100-59-33-116.compute-1.amazonaws.com"
                    if isinstance(res_list, list):
                        for res in res_list:
                            ag = res.get("agent") or {}
                            if ag:
                                ad = self.rest(f"agent/{ag.get('id','')}")
                                if "error" not in ad:
                                    props = ad.get("properties") or {}
                                    hostname = props.get("agent.host", hostname)

                    url = f"http://{hostname}:{port}" if port != "N/A" else f"http://{hostname}"
                    self.log(f"      [{ename}] -> {url}")
                    self.csv_row(sec, cat, "(D) App URLs", f"URL - {ename}", url)
            self.log()
            self.csv_row(sec, "UCD Store", "Internal Storage", "Artifact Repo",  "/opt/ibm-ucd/server/appdata/repository/")
            self.csv_row(sec, "UCD Store", "Internal Storage", "Server Log",     "/opt/ibm-ucd/server/var/log/deployserver.out")
            self.csv_row(sec, "UCD Store", "Internal Storage", "Agent Log",      "/opt/ibm-ucd/agent/var/log/agent.out")
            self.csv_row(sec, "UCD Store", "Internal Storage", "Agent Work Dir", "/opt/ibm-ucd/agent/var/work/")

        self.log()
        self.log("  UCD INTERNAL ARTIFACT STORE:")
        self.log("  +" + "-"*66 + "+")
        self.log("  |  UCD stores artifact metadata in its internal CodeStation.    |")
        self.log("  |  Physical paths on UCD server:                                |")
        self.log("  |    Artifact repo : /opt/ibm-ucd/server/appdata/repository/    |")
        self.log("  |    Server logs   : /opt/ibm-ucd/server/var/log/               |")
        self.log("  |    Agent logs    : /opt/ibm-ucd/agent/var/log/agent.out       |")
        self.log("  |    Agent work    : /opt/ibm-ucd/agent/var/work/               |")
        self.log("  |                                                                |")
        self.log("  |  Verify on EC2:                                               |")
        self.log("  |    ssh ec2 -> ls /opt/ibm-ucd/agent/var/work/                |")
        self.log("  +" + "-"*66 + "+")

    # ─── Save text report ────────────────────────────────────────────
    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.report_lines))
        print(f"\n[SAVED] Text report  : {path}")

    # ─── Save CSV report ─────────────────────────────────────────────
    def save_csv(self, path):
        """Write all collected data to a CSV file with headers.
        If the file is locked (open in Excel), auto-saves to a timestamped filename."""
        target = path
        try:
            with open(target, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.csv_headers)
                writer.writeheader()
                writer.writerows(self.csv_rows)
        except PermissionError:
            # File is open in Excel — use a timestamped filename
            ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
            base   = os.path.splitext(path)[0]
            target = f"{base}_{ts}.csv"
            print(f"[WARN] '{path}' is open (Excel?). Saving to: {target}")
            with open(target, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.csv_headers)
                writer.writeheader()
                writer.writerows(self.csv_rows)
        print(f"[SAVED] CSV report   : {target}")
        print(f"        Total rows   : {len(self.csv_rows)} application rows")


# ════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════
def main():
    import argparse
    parser = argparse.ArgumentParser(description="UCD End-to-End Application Analyzer")
    parser.add_argument("-s", "--server", default=UCD_SERVER, help="UCD server URL (default: EC2 instance)")
    parser.add_argument("-u", "--user", default=UCD_USER, help="UCD username (default: admin)")
    parser.add_argument("-p", "--password", default=UCD_PASSWORD, help="UCD password (default: admin)")
    parser.add_argument("-i", "--input", default=INPUT_FILE, help="Input file containing application names (default: app_input.txt)")
    parser.add_argument("-o", "--output", default=OUTPUT_FILE, help="Output text report file path (default: ucd_analysis_report.txt)")
    parser.add_argument("-c", "--csv", default=CSV_FILE, help="Output CSV report file path (default: ucd_analysis_report.csv)")
    
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[ERROR] '{args.input}' not found.")
        print(f"  Create '{args.input}' with the UCD application names (one per line).")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        app_names = [line.strip() for line in f if line.strip()]

    if not app_names:
        print(f"[ERROR] '{args.input}' is empty. Add the application name.")
        sys.exit(1)

    print(f"\n[INPUT] Application count: {len(app_names)}")
    print(f"[INFO]  UCD Server: {args.server}")
    print()

    analyzer = UCDAnalyzer(args.server, args.user, args.password)
    try:
        for i, app_name in enumerate(app_names, 1):
            print(f"Analyzing app {i}/{len(app_names)}: {app_name}")
            analyzer.analyze(app_name)
        analyzer.save(args.output)
        analyzer.save_csv(args.csv)
    except KeyboardInterrupt:
        print("\n[WARN] Interrupted.")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
