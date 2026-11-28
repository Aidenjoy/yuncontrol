import { dashboardApi, type DashboardApi } from "@/features/dashboard/api";
import type { DeviceRuntimeView, RuntimeTypeView } from "@/features/dashboard/types";
import type { CloudComputerStatus } from "@/features/cloud-computer/api";

export type CloudComputerProgressStage =
  | "disabled"
  | "provisioning"
  | "connector"
  | "runtime"
  | "ready"
  | "error";

export type CloudComputerProgress = {
  status: CloudComputerStatus;
  stage: CloudComputerProgressStage;
  runtime: DeviceRuntimeView | null;
};

export type CloudComputerRuntimeApi = Pick<
  DashboardApi,
  | "getConnector"
  | "discoverConnectorRuntimes"
  | "discoverConnectorRuntimeTypes"
  | "createConnectorRuntime"
  | "putConnectorRuntimeConfig"
  | "setConnectorRuntimeActive"
>;

export function isYunworkRuntimeType(value: string): boolean {
  return value.trim().toLowerCase().replace(/[\s_-]/g, "") === "yunwork";
}

export function isCloudRuntimeReady(runtime: DeviceRuntimeView): boolean {
  return isYunworkRuntimeType(runtime.runtimeType)
    && runtime.present !== false
    && runtime.available !== false
    && runtime.configured
    && runtime.active
    && runtime.status === "running";
}

export function provisioningProgress(status: CloudComputerStatus): CloudComputerProgress {
  return { status: { ...status, phase: "provisioning", error: null }, stage: "provisioning", runtime: null };
}

export async function resolveCloudComputerProgress(
  token: string,
  status: CloudComputerStatus,
  api: CloudComputerRuntimeApi = dashboardApi,
): Promise<CloudComputerProgress> {
  if (status.phase === "disabled") return { status, stage: "disabled", runtime: null };
  if (status.phase === "error") return { status, stage: "error", runtime: null };
  if (
    status.phase !== "running"
    || status.containerState !== "running"
    || !status.connectorId
  ) {
    return { status, stage: "provisioning", runtime: null };
  }

  const connectorId = status.connectorId;
  const { connector } = await api.getConnector(token, connectorId);
  if (connector.status !== "online") return { status, stage: "connector", runtime: null };

  const discovered = await api.discoverConnectorRuntimes(token, connectorId);
  let runtime = discovered.runtimes.find((item) => isYunworkRuntimeType(item.runtimeType)) ?? null;
  if (!runtime) {
    const types = await api.discoverConnectorRuntimeTypes(token, connectorId);
    const runtimeType = types.runtimeTypes.find(isAvailableYunworkRuntimeType);
    if (!runtimeType) return { status, stage: "runtime", runtime: null };
    runtime = await api.createConnectorRuntime(token, connectorId, {
      runtimeType: runtimeType.runtimeType,
      name: runtimeType.displayName || "云大师 Agent",
      config: {},
      active: true,
    });
  }

  if (!runtime.configured) {
    runtime = await api.putConnectorRuntimeConfig(token, connectorId, runtime.runtimeId, {});
  }
  if (!isCloudRuntimeReady(runtime)) {
    runtime = await api.setConnectorRuntimeActive(token, connectorId, runtime.runtimeId, true);
  }
  return {
    status,
    stage: isCloudRuntimeReady(runtime) ? "ready" : "runtime",
    runtime,
  };
}

function isAvailableYunworkRuntimeType(runtimeType: RuntimeTypeView): boolean {
  return isYunworkRuntimeType(runtimeType.runtimeType)
    && runtimeType.present
    && runtimeType.available;
}
