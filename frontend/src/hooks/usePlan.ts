import { useAuth } from "@/lib/providers";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/lib/supabase";

export type Plan = "free" | "pro";

export function usePlan() {
  const { user } = useAuth();

  const { data: profile } = useQuery({
    queryKey: ["profile", user?.id],
    queryFn: async () => {
      if (!user) return null;
      const { data } = await supabase
        .from("profiles")
        .select("plan")
        .eq("id", user.id)
        .single();
      return data;
    },
    enabled: !!user,
  });

  const plan: Plan = profile?.plan === "pro" ? "pro" : "free";
  const isPro = plan === "pro";

  return { plan, isPro, isLoggedIn: !!user };
}
