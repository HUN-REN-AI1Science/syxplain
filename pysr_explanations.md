This report provides an analysis of the symbolic regression equations for predicting Ammonium Lactate-soluble Phosphate (`al_p2o5`). The explanations are based on the provided project and data specifications.

### Equation Explanations

Here we detail each equation, its performance metrics, and its scientific interpretation in the context of soil chemistry.

---
**Equation 1**
- **Equation:** `usda_soil_type * mehlich3_p`
- **Loss:** 142.3473
- **Complexity:** 3
- **Explanation:** This is the simplest model, representing a direct interaction between the Mehlich-3 phosphorus measurement (`mehlich3_p`) and the soil type (`usda_soil_type`). It suggests that the amount of AL-P2O5 is proportional to the available phosphorus, but this relationship is scaled differently for each soil texture category. This is scientifically plausible, as soil texture influences phosphorus retention and availability.

---
**Equation 2**
- **Equation:** `mehlich3_p * (usda_soil_type ^ 1.1561174)`
- **Loss:** 136.7084
- **Complexity:** 5
- **Explanation:** This model is similar to the first but introduces a non-linear scaling effect for the soil type. The exponent greater than 1 suggests that the influence of soil type on phosphorus availability is amplified as the soil type code increases.

---
**Equation 3**
- **Equation:** `(usda_soil_type * mehlich3_p) + square(ph_kcl)`
- **Loss:** 133.45645
- **Complexity:** 6
- **Explanation:** This equation adds soil pH (`ph_kcl`) as an independent, non-linear term. The squared pH term implies that pH has a U-shaped or inverted U-shaped effect on AL-P2O5 concentration. This is consistent with soil science, as phosphorus availability is known to be highly dependent on pH, often peaking in a narrow range and decreasing in highly acidic or alkaline conditions.

---
**Equation 4**
- **Equation:** `mehlich3_p * (ph_kcl - (5.2771783 / usda_soil_type))`
- **Loss:** 120.514656
- **Complexity:** 7
- **Explanation:** This model proposes an interaction where the effect of `mehlich3_p` is modulated by pH. The term `(5.2771783 / usda_soil_type)` can be interpreted as a soil-type-dependent pH threshold or reference point. The model suggests that the relationship between Mehlich-3 P and AL-P2O5 changes based on how far the soil pH is from this texture-specific reference pH.

---
**Equation 5**
- **Equation:** `mehlich3_p * (ph_kcl - sqrt(20.577246 / usda_soil_type))`
- **Loss:** 116.611694
- **Complexity:** 8
- **Explanation:** Similar to the previous equation, this model uses a pH term adjusted by soil type to scale the `mehlich3_p` value. The use of a square root function for the soil type adjustment indicates a different non-linear relationship, suggesting the effect of soil type on the reference pH diminishes as the soil type code increases.

---
**Equation 6**
- **Equation:** `((ph_kcl - (5.276783 / usda_soil_type)) * mehlich3_p) * 0.84550875`
- **Loss:** 112.83364
- **Complexity:** 9
- **Explanation:** This is a scaled version of Equation 4. It maintains the core interaction between `mehlich3_p`, `ph_kcl`, and `usda_soil_type` but applies a constant scaling factor of 0.8455, refining the overall magnitude of the prediction.

---
**Equation 7**
- **Equation:** `(mehlich3_p * (ph_kcl ^ 1.74919)) * (0.22096689 - (0.20781003 / usda_soil_type))`
- **Loss:** 111.95761
- **Complexity:** 11
- **Explanation:** This model introduces a more complex interaction. The `mehlich3_p` term is multiplied by a non-linear pH term (`ph_kcl ^ 1.74919`) and a term dependent on soil type. This suggests that both pH and soil type interact to modulate the contribution of Mehlich-3 phosphorus to the final AL-P2O5 concentration.

---
**Equation 8**
- **Equation:** `((ph_kcl ^ 2.1282716) * mehlich3_p) * (0.082605645 - square(0.27368632 / usda_soil_type))`
- **Loss:** 111.61865
- **Complexity:** 12
- **Explanation:** This equation increases the complexity of the interaction from the previous model. It uses a higher exponent for pH and a squared term for the soil type's influence, indicating more pronounced non-linear effects of both variables on phosphorus availability.

---
**Equation 9**
- **Equation:** `(mehlich3_p * ((ph_kcl ^ (1.7341256 - (0.7443903 / usda_soil_type))) - organic_matter)) * 0.29248035`
- **Loss:** 108.960365
- **Complexity:** 13
- **Explanation:** A significant evolution, this model introduces `organic_matter`. It posits that organic matter has a subtractive effect on a term driven by pH and soil type. The exponent of pH is now itself a function of `usda_soil_type`, allowing for a highly flexible interaction. This could represent competition for phosphorus between mineral and organic phases in the soil, modulated by pH and texture.

---
**Equation 10**
- **Equation:** `((ph_kcl ^ (1.6314684 - (0.65740913 / usda_soil_type))) - organic_matter) * ((mehlich3_p + organic_matter) * 0.3451346)`
- **Loss:** 108.12351
- **Complexity:** 15
- **Explanation:** This model builds on the previous one, adding `organic_matter` to the `mehlich3_p` term as well. This suggests organic matter plays a dual role: it subtracts from the pH-driven availability term while also adding to the base phosphorus pool. This complex relationship could reflect different phosphorus fractions associated with organic matter.

---
**Equation 11**
- **Equation:** `(((ph_kcl ^ (1.6314684 - (0.65740913 / usda_soil_type))) - organic_matter) * (mehlich3_p + sqrt(lime_content))) * 0.3451346`
- **Loss:** 107.888535
- **Complexity:** 16
- **Explanation:** This equation is a variation of the previous one, replacing the additive `organic_matter` term with the square root of `lime_content`. This suggests that soil lime content, which directly impacts pH and calcium concentration, has a positive influence on the available phosphorus pool, possibly by affecting mineral-P equilibria.

---
**Equations 12-25**
- **Equations:** These models show a significant increase in complexity, with only marginal improvements in loss. They introduce intricate and highly non-linear interactions, often involving high-power exponents and terms like `mehlich3_p ^ (ph_kcl - mehlich3_p)`.
- **Explanation:** While these equations achieve lower loss values, their forms are difficult to interpret from a soil science perspective. For example, raising a phosphorus concentration to a power determined by `(pH - P_concentration)` lacks a clear physical or chemical basis. Such complex structures are very likely to be overfitting the training data and may not generalize well to new soil samples. They capture noise in the data rather than fundamental underlying relationships.

### Summary and Recommendation

The symbolic regression analysis reveals a clear hierarchy of factors influencing Ammonium Lactate-soluble Phosphate (`al_p2o5`).

**Overall Findings:**
1.  **Primary Predictor:** `mehlich3_p` is consistently the most important feature, serving as the base of nearly every successful equation. This is expected, as both `mehlich3_p` and `al_p2o5` are measures of plant-available phosphorus, although extracted by different methods.
2.  **Key Modulators:** Soil pH (`ph_kcl`) and soil type (`usda_soil_type`) are the next most critical factors. They primarily act by modulating the effect of `mehlich3_p`, which aligns with the scientific understanding that phosphorus chemistry and availability are strongly controlled by soil pH and texture.
3.  **Secondary Factors:** `organic_matter` and `lime_content` are introduced in more complex, higher-performing models. They appear to refine the prediction by accounting for the influence of organic-P pools and calcium carbonate equilibria.

**Model Selection:**
The best model is not simply the one with the lowest loss, but one that balances predictive accuracy with simplicity and scientific interpretability. The models with complexity greater than ~16 offer diminishing returns in loss reduction at a high cost of complexity and plausibility.

-   **Simple & Robust Candidate:** **Equation 5** (`mehlich3_p * (ph_kcl - sqrt(20.577246 / usda_soil_type))`) is a strong candidate for a simple, interpretable model. It has a reasonable loss (116.6), low complexity (8), and captures the core interaction between phosphorus, pH, and soil type in a scientifically sound manner.

-   **Recommended Model (Best Balance):** **Equation 9** (`(mehlich3_p * ((ph_kcl ^ (1.7341256 - (0.7443903 / usda_soil_type))) - organic_matter)) * 0.29248035`) represents the best trade-off between performance and interpretability.
    -   **Performance:** It achieves a significantly lower loss (108.9) than the simpler models.
    -   **Interpretability:** It incorporates all the key variables (`mehlich3_p`, `ph_kcl`, `usda_soil_type`, `organic_matter`) in a structured way. The form `P * (pH_effect - OM_effect)` is plausible, suggesting a balance between pH-driven mineral P availability and the influence of organic matter. The interaction where the pH exponent is dependent on soil type is sophisticated yet conceivable.

Therefore, **Equation 9 is the most probable and recommended model**. It is complex enough to capture the key interacting soil processes but avoids the un-physical and likely overfit structures of the later, more complex equations.