import { useState, useEffect, useCallback } from "react";
import { getCurrentQuarter } from "../lib/quarterUtils";
import { useLocation } from "react-router-dom";