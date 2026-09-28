import { defineStore } from "pinia";
import { http } from "@/api/client";
import type { AuthStatus, SessionInfo } from "@/api/types";

/** 会话状态：Cookie 为主，token 仅内存保留（与旧版 A7 行为一致） */
export const useAuthStore = defineStore("auth", {
  state: () => ({
    username: "",
    token: "",
    setupRequired: false,
    checked: false,
  }),
  getters: {
    isAuthed: (s) => !!s.username,
  },
  actions: {
    async fetchStatus() {
      const st = await http.get<AuthStatus>("/api/auth/status");
      this.setupRequired = st.setup_required;
      this.username = st.username || "";
      this.checked = true;
      return st;
    },
    async fetchMe() {
      const me = await http.get<{ username: string }>("/api/auth/me");
      this.username = me.username;
      return me;
    },
    /** 会话是否有效（Cookie / 内存 token） */
    async tryRestore() {
      await this.fetchStatus();
      if (this.setupRequired) return false;
      try {
        await this.fetchMe();
        return true;
      } catch {
        this.username = "";
        this.token = "";
        return false;
      }
    },
    async login(username: string, password: string) {
      const s = await http.post<SessionInfo>("/api/auth/login", { username, password });
      this.username = s.username;
      this.token = s.token || "";
      this.setupRequired = false;
      return s;
    },
    async setup(username: string, password: string) {
      const s = await http.post<SessionInfo>("/api/auth/setup", { username, password });
      this.username = s.username;
      this.token = s.token || "";
      this.setupRequired = false;
      return s;
    },
    async forgot(payload: {
      recovery_code: string;
      username?: string | null;
      new_password: string;
    }) {
      const s = await http.post<SessionInfo>("/api/auth/forgot", payload);
      this.username = s.username;
      this.token = s.token || "";
      this.setupRequired = false;
      return s;
    },
    async changePassword(oldPassword: string, newPassword: string) {
      const s = await http.post<SessionInfo>("/api/auth/change-password", {
        old_password: oldPassword,
        new_password: newPassword,
      });
      this.token = s.token || "";
      return s;
    },
    async logout() {
      try {
        await http.post("/api/auth/logout");
      } finally {
        this.username = "";
        this.token = "";
      }
    },
  },
});
