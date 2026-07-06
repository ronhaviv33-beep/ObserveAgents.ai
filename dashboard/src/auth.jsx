import { createContext, useContext } from "react";
import { T } from "./theme.js";

export const UserContext = createContext(null);
export const useUser = () => useContext(UserContext);

export const RolesContext = createContext({});
export const useRoles = () => useContext(RolesContext);

export const ROLES = {
  admin:   { label:"Admin",   color: T.crit,   pages: ["dashboard","overview_hub","surfaces_demo","welcome","agent_inventory","discovery","governance","relationship_map","runtime","intelligence","guardrails","cost","security_intel","ecosystem","budgets","pricing","security","users","apikeys","settings","home","overview","agents","models","workflows","alerts","assets","chat","integrations","onboarding"], can: ["view_all_sessions"], team_scoped: false },
  analyst: { label:"Analyst", color: T.warn,   pages: ["dashboard","overview_hub","surfaces_demo","welcome","agent_inventory","discovery","governance","relationship_map","runtime","intelligence","guardrails","cost","security_intel","ecosystem","budgets","pricing","home","overview","agents","models","workflows","alerts","assets","chat","integrations","onboarding"],                                          can: [], team_scoped: true },
  viewer:  { label:"Viewer",  color: T.info,   pages: ["dashboard","overview_hub","surfaces_demo","welcome","agent_inventory","discovery","governance","relationship_map","runtime","intelligence","guardrails","cost","security_intel","ecosystem","budgets","pricing","home","overview","agents","models","workflows","alerts","assets"],                                                                             can: [], team_scoped: true },
};

export function canSeePage(user, page, rolesMap = ROLES) {
  return (rolesMap[user?.role]?.pages ?? []).includes(page);
}

export function userCan(user, capability, rolesMap = ROLES) {
  return (rolesMap[user?.role]?.can ?? []).includes(capability);
}

export function canAccess(role, page, rolesMap = ROLES) {
  return canSeePage({ role }, page, rolesMap);
}
