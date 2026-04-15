import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://bfhmaswnkzoowfxrsfce.supabase.co";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJmaG1hc3dua3pvb3dmeHJzZmNlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYyMjI2NjAsImV4cCI6MjA5MTc5ODY2MH0.U_LlKui0FnYryfrs5NA0y7eoIE1PtP86bEjURR5qkwo";

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
