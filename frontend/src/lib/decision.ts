import { copy } from "../copy.fa";
import type { Decision } from "../types/api.gen";

export function decisionActionName(action: Decision["intent"]["action"]): string {
  switch (action) {
    case "new_search": return copy.decision.actions.new_search;
    case "refine": return copy.decision.actions.refine;
    case "change_radius": return copy.decision.actions.change_radius;
    case "change_location": return copy.decision.actions.change_location;
    case "compare": return copy.decision.actions.compare;
    case "haggle": return copy.decision.actions.haggle;
    case "ooc": return copy.decision.actions.ooc;
    case "chitchat": return copy.decision.actions.chitchat;
    default: {
      const exhaustive: never = action;
      return exhaustive;
    }
  }
}
