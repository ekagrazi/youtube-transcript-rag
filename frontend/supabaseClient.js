import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.110.8/+esm";

import { APP_CONFIG } from "./config.js";

function requirePublicConfig(name, value) {
  if (!value || value.includes("replace_me") || value.includes("your-project")) {
    throw new Error(`${name} is not configured`);
  }
  return value;
}

const supabaseUrl = requirePublicConfig(
  "Supabase URL",
  APP_CONFIG.supabaseUrl,
);
const publishableKey = requirePublicConfig(
  "Supabase publishable key",
  APP_CONFIG.supabasePublishableKey,
);

export const supabase = createClient(supabaseUrl, publishableKey, {
  auth: {
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: true,
  },
});
