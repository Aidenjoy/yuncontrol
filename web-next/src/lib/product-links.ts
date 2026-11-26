/** Fixed product configuration. Empty URLs remain visibly unavailable. */
export const PRODUCT_LINKS: {
  tokensAnywhereUrl: string
  /** External account sign-up page for the shared utoken identity service. */
  accountRegisterUrl: string
  desktopDownloadUrl: string
  landingPageUrl: string
  downloadPageUrl: string
  androidDownloadUrl: string
  iosDownloadUrl: string
  webAppHref: string
} = {
  // Tokens Anywhere's site origin, set with NEXT_PUBLIC_TOKENS_ANYWHERE_URL.
  tokensAnywhereUrl: process.env.NEXT_PUBLIC_TOKENS_ANYWHERE_URL ?? '',
  // Account creation lives on the identity provider; override for staging origins.
  accountRegisterUrl: process.env.NEXT_PUBLIC_ACCOUNT_REGISTER_URL ?? 'https://token.yundashi.com/register',
  desktopDownloadUrl: '',
  landingPageUrl: '',
  downloadPageUrl: 'https://agents-anywhere.com/download',
  androidDownloadUrl: 'https://github.com/anywhere-labs/Agents-Anywhere/releases/latest',
  iosDownloadUrl: '',
  webAppHref: '#/',
}
