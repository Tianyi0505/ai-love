import {
  Brain,
  House,
  Settings,
  Sparkles,
  UsersRound,
  type LucideIcon,
} from "lucide-react";

export type NavigationItem = {
  label: string;
  caption: string;
  path: string;
  icon: LucideIcon;
};

export const navigation: NavigationItem[] = [
  { label: "心动首页", caption: "回到她身边", path: "/", icon: House },
  { label: "灵魂底色", caption: "她是谁", path: "/personality", icon: Sparkles },
  { label: "心事手账", caption: "她记得自己", path: "/memory/self", icon: Brain },
  { label: "羁绊图鉴", caption: "她记得的人", path: "/memory/people", icon: UsersRound },
  { label: "小窝设置", caption: "守护与钥匙", path: "/settings", icon: Settings },
];
