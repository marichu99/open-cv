import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import type { AgentWithAssignment } from "@/types";

/** Admin-only: the missing other half of PATCH /api/agents/:id/activation —
 * that endpoint existed already, but nothing in the UI ever called it, so
 * approving a self-registered campaign manager required a raw API request.
 * campaign_manager is the only role left in PRIVILEGED_ROLES that
 * self-registers — aspirant was deliberately removed from that gate (the
 * aspirant answers to no admin), so it no longer shows up here. Only admins
 * can list non-agent roles (see api/agents.py's list_agents), so this card
 * is meaningless for a coordinator and the caller is expected to only
 * render it for an admin session. */
export function PendingApprovals() {
  const [pending, setPending] = useState<AgentWithAssignment[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .get<AgentWithAssignment[]>("/api/agents", { params: { role: "campaign_manager", awaiting_activation: "true" } })
      .then((res) => setPending(res.data));
  }, []);

  useEffect(() => load(), [load]);

  async function decide(id: string, activated: boolean) {
    setBusyId(id);
    try {
      await api.patch(`/api/agents/${id}/activation`, { activated });
      toast.success(activated ? "Account approved" : "Account rejected");
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not update this account");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pending approvals</CardTitle>
        <CardDescription>Self-registered campaign manager accounts can't manage agents until approved here.</CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Email</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {pending.map((a) => (
              <TableRow key={a.id}>
                <TableCell className="font-medium">{a.full_name}</TableCell>
                <TableCell className="text-muted-foreground">{a.phone_number}</TableCell>
                <TableCell className="text-muted-foreground">{a.email}</TableCell>
                <TableCell>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => decide(a.id, true)} disabled={busyId === a.id}>
                      Approve
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => decide(a.id, false)} disabled={busyId === a.id}>
                      Reject
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {pending.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                  Nothing pending.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
