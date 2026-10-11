"""Read-only TrackMan client and schema-driven query builder.

Never logs server bodies, OAuth credentials, or user records. Query gaps are
recorded rather than silently dropping fields when the upstream schema changes.
"""
import json
import os
import time

import httpx

API = "https://api.trackmangolf.com/graphql"
LOGIN = "https://login.trackmangolf.com/connect/"
CLIENT_ID = "old-golf-app.c686e909-5102-45ac-9860-8d0b789073ae"
SCOPES = "openid offline_access profile https://auth.trackman.com/dr/simulate https://auth.trackman.com/dr/cloud https://auth.trackman.com/login/autoconsent"
PAGE_SIZE = 50
TYPE_REF = "kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name } } } }"
SCHEMA_QUERY = "{__schema{types{kind name fields(includeDeprecated:true){name args{name defaultValue type{" + TYPE_REF + "}} type{" + TYPE_REF + "}} possibleTypes{name}}}}"
# Boundaries: no global discovery of other users' golf or facility administration.
BOUNDARIES = {"tournamentTeams", "participantGroups", "participantProgress", "locations", "sponsors", "partners", "availability", "rounds", "playerData", "newsFeed", "availableTournaments", "playedWith", "permissions", "playersScorecards", "otherPlayersScorecards", "participants", "teamMembers", "members", "friends", "students", "invites", "invitations", "leaderboard", "leaderboards", "players", "scores", "scorecards", "activities", "owner", "creator", "createdBy", "admins", "administrators"}
CONTEXT_FIELDS = {"facility", "bay", "location", "course", "tournament", "league", "leagueSeason", "tournamentActivity", "player", "coach", "coachProfile", "organization", "domain", "parent", "defaultFacility"}
METRIC_FIELDS = {"scorecard", "holes", "playOffHoles", "shots", "stroke", "strokes", "measurement", "normalizedMeasurement", "measurementDetails", "ballTrajectory", "clubTrajectory", "aggregatedMeasurement", "stat", "gameSettings", "puttingSettings", "clubData", "impactLocation", "data", "tests", "results", "statistics", "sessions"}
ROOTS = ("profile", "equipment", "hcp", "activities", "scorecards", "activitySummary", "performanceTests", "assignedPerformanceTests", "plannedRounds", "tournaments", "leagues", "favorites", "devices", "visits", "properties", "consents", "connectedApps", "userAccess", "coachProfile")


class TrackManError(Exception):
    pass


def oauth_form(endpoint, fields):
    try:
        response = httpx.post(LOGIN + endpoint, data={"client_id": os.getenv("TRACKMAN_CLIENT_ID", CLIENT_ID), **fields}, timeout=30)
        data = response.json()
    except (httpx.HTTPError, ValueError):
        raise TrackManError("TrackMan svarte ikke. Prøv igjen senere.") from None
    if not isinstance(data, dict):
        raise TrackManError("TrackMan ga et uventet innloggingssvar.")
    if response.is_error:
        reason = data.get("error", "oauth_error")
        if reason in {"authorization_pending", "slow_down", "access_denied", "expired_token", "invalid_grant"}:
            return {"error": reason}
        raise TrackManError("TrackMan avviste tilkoblingen. Innloggingen kan ha endret seg.")
    return data


def device_authorization():
    data = oauth_form("deviceauthorization", {"scope": SCOPES})
    required = ("device_code", "user_code", "verification_uri", "expires_in")
    if any(not data.get(key) for key in required) or data["verification_uri"] != "https://login.trackmangolf.com/device":
        raise TrackManError("TrackMan ga en ugyldig tilkoblingslenke.")
    return data


def named_type(ref):
    while ref.get("ofType"):
        ref = ref["ofType"]
    return ref


def is_list(ref):
    return ref["kind"] == "LIST" or (ref["kind"] == "NON_NULL" and is_list(ref["ofType"]))


class TrackManClient:
    def __init__(self, access_token=None, transport=None):
        self.http = httpx.Client(timeout=90, transport=transport, headers={"Authorization": "Bearer " + access_token} if access_token else {})
        self.schema = {}
        self.gaps = set()
        self.boundaries = set()
        self.pages = []
        self.max_depth = 3
        self.read_errors = []

    def close(self):
        self.http.close()

    def query(self, query, variables=None, allow_partial=False):
        if len(query.encode()) > 250000:
            raise TrackManError("TrackMan-spørringen overskred størrelsesgrensen.")
        # Bound retries; a failure never means an empty result or deletion.
        for attempt in range(4):
            try:
                response = self.http.post(API, json={"query": query, "variables": variables or {}})
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 3:
                        time.sleep(min(2 ** attempt, 8))
                        continue
                if response.status_code in (401, 403):
                    raise TrackManError("TrackMan-tilkoblingen må fornyes.")
                result = response.json()
                if response.is_error and not result.get("errors"):
                    response.raise_for_status()
            except (httpx.HTTPError, ValueError):
                if attempt < 3:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise TrackManError("Henting fra TrackMan feilet. Eksisterende arkiv er beholdt.") from None
            if result.get("errors"):
                # Deliberately fail even if GraphQL also returned partial data.
                paths = [".".join(map(str, error.get("path", []))) for error in result["errors"]]
                if allow_partial and isinstance(result.get("data"), dict) and all(paths):
                    self.gaps.update("upstream error: " + path for path in paths)
                    self.read_errors.extend(paths)
                else:
                    raise TrackManError("TrackMan returnerte en datafeil" + (" i " + ", ".join(paths[:5]) if any(paths) else "") + ".")
            if not isinstance(result.get("data"), dict):
                raise TrackManError("TrackMan returnerte ingen data.")
            return unalias(result["data"])
        raise TrackManError("TrackMan er midlertidig utilgjengelig.")

    def load_schema(self):
        result = self.query(SCHEMA_QUERY)
        self.schema = {item["name"]: item for item in result["__schema"]["types"]}
        return result["__schema"]

    def selection(self, type_name, ancestors=(), depth=0, path="", scalar_only=False, alias=False):
        definition = self.schema[type_name]
        if definition["kind"] in ("SCALAR", "ENUM"):
            return ""
        if definition["kind"] in ("INTERFACE", "UNION"):
            return "__typename " + " ".join("... on " + t["name"] + " { " + self.selection(t["name"], ancestors, depth, path, scalar_only, True) + " }" for t in definition.get("possibleTypes") or [])
        selections = ["__typename"]
        for field in definition.get("fields") or []:
            name = field["name"]
            output_name = type_name + "__" + name + ":" + name if alias else name
            field_path = (path + "." + name).strip(".")
            if name in BOUNDARIES:
                self.boundaries.add(type_name + "." + name)
                continue
            required = [a for a in field["args"] if a["type"]["kind"] == "NON_NULL" and a.get("defaultValue") is None]
            if required:
                self.gaps.add(type_name + "." + name + ": required arguments")
                continue
            target = named_type(field["type"])
            args = {a["name"] for a in field["args"]}
            suffix = "(skip:0,take:50)" if {"skip", "take"} <= args else ""
            if suffix:
                # These nested collections are expanded separately after the object read.
                self.pages.append((field_path, type_name, name))
            if target["kind"] in ("SCALAR", "ENUM"):
                selections.append(output_name + suffix)
            elif scalar_only or name in CONTEXT_FIELDS or (type_name == "HcpRecord" and name == "scorecard") or (depth >= self.max_depth and name not in METRIC_FIELDS) or depth >= 8 or target["name"] in ancestors + (type_name,):
                # Keep reference identity/scalars, and expose this boundary in the manifest.
                self.gaps.add(type_name + "." + name + ": reference/depth boundary")
                selections.append(output_name + suffix + " { " + self.identity_selection(target["name"]) + " }")
            else:
                selections.append(output_name + suffix + " { " + self.selection(target["name"], ancestors + (type_name,), depth + 1, field_path) + " }")
            if target["name"] == "KeyValuePairOfStringAndObject":
                self.gaps.add(type_name + "." + name + ": TrackMan exposes keys but no values")
        result = " ".join(selections)
        if depth == 0 and len(result) > 250000:
            raise TrackManError("TrackMan-skjemaet gir en for stor spørring. Ingen spørring ble sendt.")
        return result

    def bounded_selection(self, type_name, path=""):
        # TrackMan also caps documents at 2048 fields. Thin context graphs,
        # retaining deep explicit measurement paths, before sending any query.
        import re
        saved_depth = self.max_depth
        saved_gaps = set(self.gaps)
        try:
            for limit in (3, 2, 1, 0):
                self.max_depth = limit
                self.gaps = set(saved_gaps)
                try:
                    result = self.selection(type_name, path=path)
                except TrackManError:
                    continue
                fields = selection_field_count(result)
                if fields < 1850 and len(result) < 240000:
                    return result
            raise TrackManError("TrackMan-skjemaet overskrider spørringsgrensen.")
        finally:
            self.max_depth = saved_depth

    def identity_selection(self, type_name, alias=False):
        definition = self.schema[type_name]
        if definition["kind"] in ("INTERFACE", "UNION"):
            return "__typename " + " ".join("... on " + t["name"] + " { " + self.identity_selection(t["name"], True) + " }" for t in definition.get("possibleTypes") or [])
        return "__typename " + " ".join((type_name + "__" + f["name"] + ":" + f["name"] if alias else f["name"]) for f in definition.get("fields") or [] if named_type(f["type"])["kind"] in ("SCALAR", "ENUM") and not f["args"])

    def root(self, name, skip=0, detail=True):
        self.read_errors = []
        field = next((f for f in self.schema["Me"]["fields"] if f["name"] == name), None)
        if not field:
            raise TrackManError("TrackMan mangler datakilden " + name + ".")
        if any(a["type"]["kind"] == "NON_NULL" and a.get("defaultValue") is None for a in field["args"]):
            self.gaps.add("Me." + name + ": required arguments")
            return None, False
        args = {a["name"] for a in field["args"]}
        paging = {"skip", "take"} <= args
        options = ["skip:" + str(skip), "take:50"] if paging else []
        if name == "activities":
            options.append("includeHidden:true")
        suffix = "(" + ",".join(options) + ")" if options else ""
        target = named_type(field["type"])["name"]
        selection = self.bounded_selection(target, path=name) if detail else ("items { __typename id kind time } pageInfo { hasNextPage } totalCount" if name == "activities" else "__typename id")
        return self.query("{ me { " + name + suffix + " { " + selection + " } } }", allow_partial=detail)["me"][name], paging

    def node(self, identity, type_name):
        self.pages = []
        self.read_errors = []
        selection = self.bounded_selection(type_name)
        record = self.query("query($id:ID!){ node(id:$id){ ... on " + type_name + " { " + selection + " } } }", {"id": identity}, allow_partial=True)["node"]
        if record is None:
            raise TrackManError("TrackMan kunne ikke åpne en oppført aktivitet/runde.")
        self.expand_pages(record, "node(id:" + json.dumps(identity) + ")", type_name)
        return record

    def expand_pages(self, record, expression, type_name):
        expression = [expression] if isinstance(expression, str) else expression
        """Expand nested offset collections through scalar object paths, or node IDs.

        Lists are walked using the nearest Node identity so scorecard event logs,
        handicap history and media aren't truncated at an implicit first page.
        """
        if not isinstance(record, dict):
            return
        fields = {f["name"]: f for f in self.schema.get(type_name, {}).get("fields") or []}
        for name, value in list(record.items()):
            field = fields.get(name)
            if not field or not isinstance(value, (dict, list)):
                continue
            target = named_type(field["type"])["name"]
            args = {a["name"] for a in field["args"]}
            if {"skip", "take"} <= args:
                selection = self.bounded_selection(target)
                combined = items_of(value)
                total = value.get("totalCount") if isinstance(value, dict) else None
                seen = {json.dumps(v, sort_keys=True) for v in combined}
                offset = len(combined)
                more = has_next(value, len(combined))
                while more:
                    if offset > 1000000:
                        raise TrackManError("TrackMan-pagineringen overskred sikkerhetsgrensen.")
                    sub = name + "(skip:" + str(offset) + ",take:50) { " + selection + " }"
                    body = "... on " + type_name + " { " + sub + " }"
                    for step in reversed(expression):
                        body = step + " { " + body + " }"
                    result = self.query("{ " + body + " }", allow_partial=True)
                    for step in expression:
                        result = result[step.split("(")[0]]
                    page = result[name]
                    batch = items_of(page)
                    if not batch and has_next(page, 0):
                        raise TrackManError("TrackMan returnerte en tom side før siste side.")
                    if any(json.dumps(v, sort_keys=True) in seen for v in batch):
                        raise TrackManError("TrackMan gjentok en dataside. Synken er ikke komplett.")
                    seen.update(json.dumps(v, sort_keys=True) for v in batch)
                    combined.extend(batch)
                    offset += len(batch)
                    more = has_next(page, len(batch))
                if total is not None and len(combined) != total:
                    raise TrackManError("TrackMan-antallet stemmer ikke med antall hentede poster.")
                if isinstance(value, dict):
                    value["items"] = combined
                    value["pageInfo"] = {**(value.get("pageInfo") or {}), "hasNextPage": False}
                else:
                    record[name] = combined
                value = record[name]
            children = value if isinstance(value, list) else [value]
            for child in children:
                if not isinstance(child, dict):
                    continue
                actual = child.get("__typename", target)
                child_fields = self.schema.get(actual, {}).get("fields") or []
                if child.get("id") and actual in self.node_types():
                    self.expand_pages(child, ["node(id:" + json.dumps(child["id"]) + ")"], actual)
                elif not isinstance(value, list):
                    self.expand_pages(child, expression + [name], actual)
                elif any({"skip", "take"} <= {a["name"] for a in f["args"]} for f in child_fields):
                    self.gaps.add(actual + ": nested pagination needs a Node identity")

    def node_types(self):
        return {t["name"] for t in self.schema.get("Node", {}).get("possibleTypes") or []}


def items_of(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return value.get("items") or []
    return []


def has_next(value, count):
    if isinstance(value, dict) and isinstance(value.get("pageInfo"), dict) and "hasNextPage" in value["pageInfo"]:
        return value["pageInfo"]["hasNextPage"] is True
    return count >= PAGE_SIZE


def unalias(value):
    if isinstance(value, list):
        return [unalias(v) for v in value]
    if isinstance(value, dict):
        return {(k.split("__", 1)[1] if "__" in k and not k.startswith("__") else k): unalias(v) for k, v in value.items()}
    return value


def selection_field_count(selection):
    import re
    tokens = re.findall(r'\.\.\.|[A-Za-z_]\w*|[{}():]|[0-9]+|"[^"]*"', selection)
    position = 0
    def block():
        nonlocal position
        count = 0
        while position < len(tokens) and tokens[position] != "}":
            if tokens[position] == "...":
                position += 3  # ... on ConcreteType
            else:
                position += 1
                if position < len(tokens) and tokens[position] == ":":
                    position += 2  # alias : actualField
                count += 1
            if position < len(tokens) and tokens[position] == "(":
                level = 1
                position += 1
                while position < len(tokens) and level:
                    level += (tokens[position] == "(") - (tokens[position] == ")")
                    position += 1
            if position < len(tokens) and tokens[position] == "{":
                position += 1
                count += block()
                position += 1
        return count
    return block()
