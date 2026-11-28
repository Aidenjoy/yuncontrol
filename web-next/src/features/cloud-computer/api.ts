import { ApiClient, apiClient } from "@/lib/api";

export type CloudComputerPhase = "disabled" | "provisioning" | "running" | "error";

export type CloudComputerStatus = {
  configured: boolean;
  phase: CloudComputerPhase;
  containerState: string;
  connectorId: string | null;
  displayName: string;
  updatedAt: string | null;
  error: string | null;
};

export class CloudComputerApi {
  constructor(private readonly client: ApiClient = apiClient) {}

  get(token: string): Promise<CloudComputerStatus> {
    return this.client.get<CloudComputerStatus>("/cloud-computer", { token });
  }

  enable(token: string): Promise<CloudComputerStatus> {
    return this.client.post<CloudComputerStatus>("/cloud-computer", {}, { token });
  }

  disable(token: string): Promise<CloudComputerStatus> {
    return this.client.delete<CloudComputerStatus>("/cloud-computer", { token });
  }
}

export const cloudComputerApi = new CloudComputerApi();
