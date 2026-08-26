import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useCounties, useConstituencies, useWards, useStations } from "@/lib/hooks";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { positionLabel } from "@/lib/utils";
import type { ElectivePosition, FormSubmission } from "@/types";

function AgentSignInPrompt() {
  return (
    <Card className="mx-auto max-w-sm">
      <CardHeader className="items-center text-center">
        <CardTitle>Sign in to upload</CardTitle>
        <CardDescription>Agents sign in the same way as everyone else — with a one-time code.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Link to="/login">
          <Button className="w-full">Sign in</Button>
        </Link>
        <p className="text-center text-xs text-muted-foreground">
          Not signed up yet?{" "}
          <Link to="/" className="underline underline-offset-2">
            Create an account
          </Link>{" "}
          first.
        </p>
      </CardContent>
    </Card>
  );
}

const STATUS_LABEL: Record<string, { label: string; variant: "success" | "warning" | "destructive" | "neutral" }> = {
  draft: { label: "Draft", variant: "neutral" },
  auto_approved: { label: "Auto-approved", variant: "success" },
  pending_review: { label: "Pending review", variant: "warning" },
  manually_approved: { label: "Approved by reviewer", variant: "success" },
  rejected: { label: "Rejected", variant: "destructive" },
  duplicate: { label: "Flagged as duplicate", variant: "destructive" },
};

function FilePreview({ file }: { file: File }) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const isImage = file.type.startsWith("image/");
  const isPdf = file.type === "application/pdf";

  useEffect(() => {
    const url = URL.createObjectURL(file);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  if (!objectUrl) return null;

  if (isImage) {
    return (
      <img
        src={objectUrl}
        alt="Selected form preview"
        className="max-h-80 w-full rounded-md border border-border object-contain"
      />
    );
  }
  if (isPdf) {
    return <iframe src={objectUrl} title="Selected form preview" className="h-80 w-full rounded-md border border-border" />;
  }
  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-muted p-3 text-sm">
      <span className="font-medium">File selected:</span>
      <span className="text-muted-foreground">{file.name}</span>
    </div>
  );
}

function UploadForm() {
  const { agent } = useAuth();
  const [myPositions, setMyPositions] = useState<ElectivePosition[]>([]);
  const [selectedPositionId, setSelectedPositionId] = useState<string | null>(null);

  const [countyId, setCountyId] = useState<string | null>(null);
  const [constituencyId, setConstituencyId] = useState<string | null>(null);
  const [wardId, setWardId] = useState<string | null>(null);
  const [stationId, setStationId] = useState<string | null>(null);
  const [prefilled, setPrefilled] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<FormSubmission | null>(null);
  const [busy, setBusy] = useState(false);

  const counties = useCounties();
  const constituencies = useConstituencies(countyId);
  const wards = useWards(constituencyId);
  const stations = useStations(wardId);

  // An agent posted at one station commonly tracks several simultaneous
  // races — each upload is for exactly one of them, so pick a sensible
  // default (the first) but let it be changed when there's more than one.
  useEffect(() => {
    if (!agent?.position_ids.length) return;
    api.get<ElectivePosition[]>("/api/positions").then((res) => {
      const mine = res.data.filter((p) => agent.position_ids.includes(p.id));
      setMyPositions(mine);
      setSelectedPositionId((prev) => prev ?? mine[0]?.id ?? null);
    });
  }, [agent?.position_ids]);

  // Default to the campaign-manager-assigned station, still editable — an
  // agent might legitimately cover more than one station in a day.
  useEffect(() => {
    if (!agent?.assigned_station_id || prefilled) return;
    setPrefilled(true);
    api.get(`/api/geography/stations/${agent.assigned_station_id}/ancestors`).then((res) => {
      const { station, ward, constituency, county } = res.data;
      if (county) setCountyId(county.id);
      if (constituency) setConstituencyId(constituency.id);
      if (ward) setWardId(ward.id);
      if (station) setStationId(station.id);
    });
  }, [agent?.assigned_station_id, prefilled]);

  const missingPosition = !agent?.position_ids.length;

  async function upload() {
    if (!file || !stationId || !selectedPositionId) {
      toast.error("Pick a station, a race, and choose a photo first");
      return;
    }
    setBusy(true);
    setPreview(null);
    try {
      const form = new FormData();
      form.append("station_id", stationId);
      form.append("position_id", selectedPositionId);
      form.append("image", file);
      const res = await api.post<FormSubmission>("/api/submissions/draft", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreview(res.data);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!preview) return;
    setBusy(true);
    try {
      const res = await api.post<FormSubmission>(`/api/submissions/${preview.id}/finalize`);
      setPreview(res.data);
      const status = STATUS_LABEL[res.data.status];
      toast.success(`Submitted — ${status?.label ?? res.data.status}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Submit failed");
    } finally {
      setBusy(false);
    }
  }

  function resetForCapture() {
    setFile(null);
    setPreview(null);
  }

  return (
    <div className="grid gap-6 md:grid-cols-[320px_1fr]">
      <Card className="h-fit">
        <CardHeader>
          <CardTitle>Tally333</CardTitle>
          <CardDescription>Signed in as {agent?.full_name}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>Elective position</Label>
            {myPositions.length === 0 ? (
              <p className="text-xs text-warning">
                No position assigned yet — contact your campaign manager before uploading.
              </p>
            ) : myPositions.length === 1 ? (
              <Badge variant="neutral" className="w-fit">
                {positionLabel(myPositions[0].name)}
              </Badge>
            ) : (
              <Select value={selectedPositionId ?? ""} onValueChange={setSelectedPositionId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a race" />
                </SelectTrigger>
                <SelectContent>
                  {myPositions.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {positionLabel(p.name)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>County</Label>
            <Select
              value={countyId ?? ""}
              onValueChange={(v) => {
                setCountyId(v);
                setConstituencyId(null);
                setWardId(null);
                setStationId(null);
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select county" />
              </SelectTrigger>
              <SelectContent>
                {counties.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Constituency</Label>
            <Select
              value={constituencyId ?? ""}
              onValueChange={(v) => {
                setConstituencyId(v);
                setWardId(null);
                setStationId(null);
              }}
              disabled={!countyId}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select constituency" />
              </SelectTrigger>
              <SelectContent>
                {constituencies.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Ward</Label>
            <Select
              value={wardId ?? ""}
              onValueChange={(v) => {
                setWardId(v);
                setStationId(null);
              }}
              disabled={!constituencyId}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select ward" />
              </SelectTrigger>
              <SelectContent>
                {wards.map((w) => (
                  <SelectItem key={w.id} value={w.id}>
                    {w.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Polling station</Label>
            <Select value={stationId ?? ""} onValueChange={setStationId} disabled={!wardId}>
              <SelectTrigger>
                <SelectValue placeholder="Select station" />
              </SelectTrigger>
              <SelectContent>
                {stations.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Capture &amp; submit</CardTitle>
          <CardDescription>
            Photograph the signed form, or upload a scanned PDF, preview it, confirm the extracted figures, then submit.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          {!preview && (
            <div className="relative flex flex-col gap-3">
              <Label htmlFor="image">Form photo or PDF</Label>
              <Input
                id="image"
                type="file"
                accept="image/*,application/pdf"
                capture="environment"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <p className="text-xs text-muted-foreground">
                A PDF is converted to an image automatically — only the first page is used.
              </p>

              {file && <FilePreview file={file} />}

              <Button onClick={upload} disabled={busy || !file || !stationId || !selectedPositionId || missingPosition}>
                {busy ? "Reading form…" : "Upload & extract"}
              </Button>

              {busy && (
                <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 rounded-md bg-card/95 backdrop-blur-sm">
                  <Loader2 className="size-8 animate-spin text-primary" />
                  <span className="text-sm font-medium text-foreground">Reading form…</span>
                </div>
              )}
            </div>
          )}

          {preview && (
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Extracted preview</span>
                <Badge variant={STATUS_LABEL[preview.status]?.variant ?? "neutral"}>
                  {STATUS_LABEL[preview.status]?.label ?? preview.status}
                </Badge>
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Candidate</TableHead>
                    <TableHead className="text-right">Votes</TableHead>
                    <TableHead className="text-right">Confidence</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.vote_records?.map((v) => (
                    <TableRow key={v.id}>
                      <TableCell>{v.candidate_name}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{v.effective_votes}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        <span className={v.field_confidence < 85 ? "text-warning" : "text-primary"}>
                          {v.field_confidence.toFixed(0)}%
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                  <TableRow>
                    <TableCell className="font-medium">Rejected ballots</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{preview.rejected_ballots}</TableCell>
                    <TableCell />
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">Total votes cast</TableCell>
                    <TableCell className="text-right font-mono tabular-nums font-semibold">
                      {preview.total_votes_cast}
                    </TableCell>
                    <TableCell />
                  </TableRow>
                </TableBody>
              </Table>

              {preview.warnings.length > 0 && (
                <div className="rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
                  {preview.warnings.join(" · ")}
                </div>
              )}

              {preview.status === "draft" ? (
                <div className="flex gap-2">
                  <Button onClick={confirm} disabled={busy}>
                    {busy ? "Submitting…" : "Confirm & submit"}
                  </Button>
                  <Button variant="outline" onClick={resetForCapture} disabled={busy}>
                    Retake
                  </Button>
                </div>
              ) : (
                <Button variant="outline" onClick={resetForCapture}>
                  Upload another form
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function UploadPage() {
  const { agent, loading } = useAuth();
  if (loading) return null;
  return agent ? <UploadForm /> : <AgentSignInPrompt />;
}
