/** Aliases over the generated OpenAPI types — never hand-write API shapes. */
import type { components, paths } from './schema';

type Schemas = components['schemas'];

export type DocumentOut = Schemas['DocumentOut'];
export type DocumentStatus = DocumentOut['status'];
export type DocumentList = Schemas['DocumentList'];
export type UploadAccepted = Schemas['UploadAccepted'];
export type Extraction = Schemas['ExtractionOut'];
export type InvoiceData = Schemas['InvoiceExtraction'];
export type StringField = Schemas['StringField'];
export type NumberField = Schemas['NumberField'];
export type DateField = Schemas['DateField'];
export type LineItem = Schemas['LineItem'];
export type ValidationIssue = Schemas['ValidationIssue'];
export type CorrectionRequest = Schemas['CorrectionRequest'];
export type AppSettings = Schemas['SettingsOut'];
export type WebhookEndpoint = Schemas['WebhookEndpointOut'];
export type WebhookEndpointIn = Schemas['WebhookEndpointIn'];
export type WebhookDelivery = Schemas['WebhookDeliveryOut'];
export type Sample = Schemas['SampleOut'];
export type AccuracyReport = Schemas['AccuracyReport'];
export type Problem = Schemas['Problem'];
export type DocumentListQuery = NonNullable<
  paths['/api/v1/documents']['get']['parameters']['query']
>;
export type ExportFormat = NonNullable<
  NonNullable<paths['/api/v1/exports']['get']['parameters']['query']>['format']
>;

export function isProcessing(status: DocumentStatus): boolean {
  return status === 'queued' || status === 'processing';
}
