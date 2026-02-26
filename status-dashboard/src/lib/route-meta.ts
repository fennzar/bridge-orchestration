export type FieldDef = {
  name: string;
  type: string;
  required?: boolean;
  description: string;
};

export type RouteMeta = {
  title: string;
  category: "Status" | "Chain" | "Operations" | "Testing" | "Apps";
  description: string;
  sse?: boolean;
  request?: FieldDef[];
  response?: FieldDef[];
  curl: string | string[];
};
