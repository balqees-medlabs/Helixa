"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { EmptyState } from "@/components/EmptyState";
import { GateError } from "@/components/GateError";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useCreateVendor, useUpdateVendor, useVendors } from "@/lib/features/vendors/queries";
import type { Vendor } from "@/lib/features/vendors/queries";
import { sentenceCase } from "@/lib/i18n/dir";
import { cn } from "@/lib/utils";

type TatAnchor = "receipt" | "sequencing";

const ANCHORS: Array<{ value: TatAnchor; label: string }> = [
  { value: "receipt", label: "Receipt" },
  { value: "sequencing", label: "Sequencing" },
];

interface FormState {
  name: string;
  tatDays: string;
  tatAnchor: TatAnchor;
  isActive: boolean;
}

const EMPTY_FORM: FormState = {
  name: "",
  tatDays: "21",
  tatAnchor: "receipt",
  isActive: true,
};

export default function VendorsPage() {
  const { can, isLoading } = useAuth();
  const isAdmin = can("admin");

  const vendorsQuery = useVendors();
  const createVendor = useCreateVendor();
  const updateVendor = useUpdateVendor();

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [editing, setEditing] = useState<Vendor | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const vendors = vendorsQuery.data ?? [];
  const pending = createVendor.isPending || updateVendor.isPending;

  if (isLoading) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading…
      </p>
    );
  }

  function startEdit(vendor: Vendor) {
    setEditing(vendor);
    setError(null);
    setSuccess(null);
    setForm({
      name: vendor.name,
      tatDays: String(vendor.tat_days),
      tatAnchor: vendor.tat_anchor === "sequencing" ? "sequencing" : "receipt",
      isActive: vendor.is_active,
    });
  }

  function cancelEdit() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setError(null);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    const name = form.name.trim();
    if (!name) {
      setError("Enter the vendor name.");
      return;
    }
    const tatDays = Number(form.tatDays);
    if (!Number.isInteger(tatDays) || tatDays < 0) {
      setError("Enter a whole number of turnaround days (0 or more).");
      return;
    }

    const body = {
      name,
      tat_days: tatDays,
      tat_anchor: form.tatAnchor,
      is_active: form.isActive,
    };

    const onError = (mutationError: unknown) =>
      setError(
        mutationError instanceof ApiError
          ? mutationError.detail
          : "Could not save the vendor. Please try again.",
      );

    if (editing) {
      updateVendor.mutate(
        { vendorId: editing.id, body },
        {
          onSuccess: (vendor) => {
            setEditing(null);
            setForm(EMPTY_FORM);
            setSuccess(`${vendor.name} updated.`);
          },
          onError,
        },
      );
      return;
    }

    createVendor.mutate(body, {
      onSuccess: (vendor) => {
        setForm(EMPTY_FORM);
        setSuccess(`${vendor.name} added.`);
      },
      onError,
    });
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Vendors</h1>
        <p className="text-sm text-muted-foreground">
          External sequencing partners and their turnaround targets. Everyone can view them;
          administrators can add and edit.
        </p>
      </div>

      {vendorsQuery.isLoading ? (
        <p role="status" className="text-sm text-muted-foreground">
          Loading vendors…
        </p>
      ) : vendorsQuery.isError ? (
        <GateError
          detail={
            vendorsQuery.error instanceof ApiError
              ? vendorsQuery.error.detail
              : "Could not load vendors. Please try again."
          }
        />
      ) : vendors.length === 0 ? (
        <EmptyState
          title="No vendors yet"
          description={
            isAdmin
              ? "Add the first external vendor below."
              : "An administrator has not configured any external vendors."
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">External vendors</caption>
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                <th scope="col" className="px-4 py-2 text-start font-medium">
                  Vendor
                </th>
                <th scope="col" className="px-4 py-2 text-start font-medium">
                  TAT (days)
                </th>
                <th scope="col" className="px-4 py-2 text-start font-medium">
                  Anchor
                </th>
                <th scope="col" className="px-4 py-2 text-start font-medium">
                  Status
                </th>
                {isAdmin ? (
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    Actions
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {vendors.map((vendor) => (
                <tr key={vendor.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 font-medium">{vendor.name}</td>
                  <td className="px-4 py-3 tabular-nums">{vendor.tat_days}</td>
                  <td className="px-4 py-3">{sentenceCase(vendor.tat_anchor)}</td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs font-medium",
                        vendor.is_active
                          ? "bg-success/10 text-success"
                          : "bg-secondary text-secondary-foreground",
                      )}
                    >
                      {vendor.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  {isAdmin ? (
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => startEdit(vendor)}
                        className="rounded-md border border-input px-2 py-1 text-xs hover:bg-secondary"
                      >
                        Edit
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {isAdmin ? (
        <form
          onSubmit={handleSubmit}
          className="flex max-w-2xl flex-col gap-4 rounded-lg border border-border bg-card p-4"
        >
          <h2 className="text-lg font-semibold tracking-tight">
            {editing ? `Edit ${editing.name}` : "Add vendor"}
          </h2>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="vendor_name" className="text-sm font-medium">
                Vendor name
              </label>
              <input
                id="vendor_name"
                name="vendor_name"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="vendor_tat_days" className="text-sm font-medium">
                TAT days
              </label>
              <input
                id="vendor_tat_days"
                name="vendor_tat_days"
                type="number"
                min={0}
                step={1}
                value={form.tatDays}
                onChange={(event) => setForm({ ...form, tatDays: event.target.value })}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm tabular-nums"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="vendor_anchor" className="text-sm font-medium">
                TAT anchor
              </label>
              <select
                id="vendor_anchor"
                name="vendor_anchor"
                value={form.tatAnchor}
                onChange={(event) =>
                  setForm({ ...form, tatAnchor: event.target.value as TatAnchor })
                }
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
              >
                {ANCHORS.map((anchor) => (
                  <option key={anchor.value} value={anchor.value}>
                    {anchor.label}
                  </option>
                ))}
              </select>
            </div>

            <label className="flex items-end gap-2 pb-1.5 text-sm">
              <input
                type="checkbox"
                checked={form.isActive}
                onChange={(event) => setForm({ ...form, isActive: event.target.checked })}
              />
              Active
            </label>
          </div>

          <GateError detail={error} />
          {success ? (
            <p
              role="status"
              className="rounded-md border border-success/30 bg-success/5 px-3 py-2 text-sm text-success"
            >
              {success}
            </p>
          ) : null}

          <div className="flex items-center gap-3">
            <SubmitButton pending={pending} pendingLabel="Saving…">
              {editing ? "Save changes" : "Add vendor"}
            </SubmitButton>
            {editing ? (
              <button
                type="button"
                onClick={cancelEdit}
                className="text-sm text-muted-foreground hover:text-brand"
              >
                Cancel
              </button>
            ) : null}
          </div>
        </form>
      ) : null}
    </section>
  );
}
