#!/usr/bin/env bash
# source refresh_token.sh  -> re-issues BEARER_TOKEN (Cognito access tokens last ~1h)
export BEARER_TOKEN=$(aws cognito-idp initiate-auth --client-id "$CLIENT_ID" --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=$USERNAME,PASSWORD="$PASSWORD" --region $REGION | jq -r '.AuthenticationResult.AccessToken')
