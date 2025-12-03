/**
 * Slack integration i18n messages
 * Modular i18n for Slack SaaS integration
 */

export const slackZhTW = {
  connectSlack: '連接 Slack',
  slackConnectionSuccess: 'Slack 連接成功',
  selectSlackAuthMethod: '選擇認證方式',
  slackOAuthDescription: '透過 Slack App 進行安全的 OAuth 認證',
  slackTokenDescription: '直接使用存取權杖認證（機器人權杖 xoxb- 或使用者權杖 xoxp-）',
  slackClientID: 'Slack Client ID（選填）',
  slackClientIDDescription: '從 Slack App 設定中取得（api.slack.com/apps）。如未提供，將使用環境變數 SLACK_CLIENT_ID。',
  slackOAuthFlowNote: '點擊「連接」後，將重新導向至 Slack 進行授權。',
  slackAccessToken: 'Slack 存取權杖',
  slackAccessTokenDescription: '機器人權杖（xoxb-）或使用者權杖（xoxp-）。從 api.slack.com/apps 取得',
};

export const slackEn = {
  connectSlack: 'Connect Slack',
  slackConnectionSuccess: 'Slack connected successfully',
  selectSlackAuthMethod: 'Select Authentication Method',
  slackOAuthDescription: 'Secure OAuth authentication via Slack App',
  slackTokenDescription: 'Direct access token authentication (bot token xoxb- or user token xoxp-)',
  slackClientID: 'Slack Client ID (Optional)',
  slackClientIDDescription: 'Get this from your Slack App settings (api.slack.com/apps). If not provided, will use SLACK_CLIENT_ID from environment.',
  slackOAuthFlowNote: 'After clicking "Connect", you will be redirected to Slack to authorize the connection.',
  slackAccessToken: 'Slack Access Token',
  slackAccessTokenDescription: 'Bot token (xoxb-) or user token (xoxp-). Get from api.slack.com/apps',
};

export const slackJa = {
  connectSlack: 'Slack に接続',
  slackConnectionSuccess: 'Slack の接続に成功しました',
  selectSlackAuthMethod: '認証方法を選択',
  slackOAuthDescription: 'Slack App による安全な OAuth 認証',
  slackTokenDescription: '直接アクセストークン認証（ボットトークン xoxb- またはユーザートークン xoxp-）',
  slackClientID: 'Slack Client ID（オプション）',
  slackClientIDDescription: 'Slack App 設定から取得（api.slack.com/apps）。提供されない場合、環境変数 SLACK_CLIENT_ID を使用します。',
  slackOAuthFlowNote: '「接続」をクリックすると、Slack にリダイレクトされて認証が行われます。',
  slackAccessToken: 'Slack アクセストークン',
  slackAccessTokenDescription: 'ボットトークン（xoxb-）またはユーザートークン（xoxp-）。api.slack.com/apps から取得',
};

