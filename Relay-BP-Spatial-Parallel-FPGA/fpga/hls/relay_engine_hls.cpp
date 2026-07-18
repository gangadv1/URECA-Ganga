/*
 * Relay engine HLS model for Xilinx Vitis HLS.
 *
 * This file is intentionally synthesizable and hardware-oriented. It models
 * the Relay lane as a cycle-driven engine built from modular helper functions:
 *   - variable_node_update
 *   - check_node_update
 *   - relay_memory_update
 *   - syndrome_check
 *
 * The code uses fixed-width integer types, explicit array partitioning, and
 * HLS pragmas so that it can be mapped to FPGA hardware later.
 */

#include <ap_int.h>

static const int MAX_VARIABLES = 16;
static const int MAX_CHECKS = 8;
static const int MAX_LEGS = 4;
static const int MAX_CYCLES_PER_LEG = 8;
static const int GAMMA_SCALE = 256;

typedef ap_int<16> llr_t;
typedef ap_int<16> gamma_t;
typedef ap_uint<1> bit_t;
typedef ap_uint<4> leg_index_t;
typedef ap_uint<8> carry_t;
typedef ap_uint<16> cycle_t;
typedef ap_uint<16> score_t;

struct RelayLegConfigHLS {
    gamma_t gamma_schedule[MAX_CYCLES_PER_LEG];
    carry_t carry_factor;
    ap_uint<4> schedule_length;
};

struct RelayEngineResultHLS {
    bit_t converged;
    ap_uint<1> valid;
    leg_index_t legs_used;
    cycle_t total_iterations;
    cycle_t convergence_cycle;
    cycle_t total_cycles;
    score_t residual_score;
    bit_t candidate_vector[MAX_VARIABLES];
};

static llr_t abs_llr(llr_t value) {
    return (value < 0) ? -value : value;
}

static bit_t hard_decision(llr_t value) {
    return (value < 0) ? bit_t(1) : bit_t(0);
}

/*
 * Variable node update:
 *  - combines prior LLR, incoming check messages, and relay memory
 *  - emits updated variable beliefs
 *  - produces variable-to-check messages for the next check update stage
 */
static void variable_node_update(
    const bit_t h_matrix[MAX_CHECKS][MAX_VARIABLES],
    const llr_t prior_llr[MAX_VARIABLES],
    const llr_t relay_memory[MAX_VARIABLES],
    const llr_t check_to_var[MAX_CHECKS][MAX_VARIABLES],
    const gamma_t gamma,
    llr_t variable_belief[MAX_VARIABLES],
    llr_t var_to_check[MAX_CHECKS][MAX_VARIABLES]) {
#pragma HLS INLINE off

    for (int variable_index = 0; variable_index < MAX_VARIABLES; ++variable_index) {
#pragma HLS PIPELINE II=1
        llr_t incoming_sum = 0;

        for (int check_index = 0; check_index < MAX_CHECKS; ++check_index) {
#pragma HLS UNROLL
            if (h_matrix[check_index][variable_index] == 1) {
                incoming_sum += check_to_var[check_index][variable_index];
            }
        }

        llr_t relay_term = (relay_memory[variable_index] * gamma) / GAMMA_SCALE;
        variable_belief[variable_index] = prior_llr[variable_index] + incoming_sum + relay_term;

        for (int check_index = 0; check_index < MAX_CHECKS; ++check_index) {
#pragma HLS UNROLL
            if (h_matrix[check_index][variable_index] == 1) {
                var_to_check[check_index][variable_index] =
                    variable_belief[variable_index] - check_to_var[check_index][variable_index];
            } else {
                var_to_check[check_index][variable_index] = 0;
            }
        }
    }
}

/*
 * Check node update:
 *  - applies a min-sum style update rule
 *  - reads all variable-to-check messages and emits check-to-variable messages
 */
static void check_node_update(
    const bit_t h_matrix[MAX_CHECKS][MAX_VARIABLES],
    const bit_t syndrome[MAX_CHECKS],
    const llr_t var_to_check[MAX_CHECKS][MAX_VARIABLES],
    llr_t check_to_var[MAX_CHECKS][MAX_VARIABLES]) {
#pragma HLS INLINE off

    for (int check_index = 0; check_index < MAX_CHECKS; ++check_index) {
#pragma HLS PIPELINE II=1
        for (int variable_index = 0; variable_index < MAX_VARIABLES; ++variable_index) {
#pragma HLS UNROLL
            if (h_matrix[check_index][variable_index] == 1) {
                ap_int<2> sign_product = 1;
                llr_t min_abs = 32767;

                for (int neighbor_index = 0; neighbor_index < MAX_VARIABLES; ++neighbor_index) {
#pragma HLS UNROLL
                    if (neighbor_index != variable_index && h_matrix[check_index][neighbor_index] == 1) {
                        llr_t message = var_to_check[check_index][neighbor_index];
                        if (message < 0) {
                            sign_product = -sign_product;
                        }
                        llr_t abs_message = abs_llr(message);
                        if (abs_message < min_abs) {
                            min_abs = abs_message;
                        }
                    }
                }

                if (min_abs == 32767) {
                    min_abs = 0;
                }

                llr_t syndrome_sign = (syndrome[check_index] == 1) ? -1 : 1;
                check_to_var[check_index][variable_index] =
                    syndrome_sign * sign_product * min_abs;
            } else {
                check_to_var[check_index][variable_index] = 0;
            }
        }
    }
}

/*
 * Relay memory update:
 *  - carries soft state from the current leg into the next leg
 *  - updates the lane-local memory vector and candidate bits
 */
static void relay_memory_update(
    const RelayLegConfigHLS &leg_config,
    const llr_t variable_belief[MAX_VARIABLES],
    const llr_t current_memory[MAX_VARIABLES],
    llr_t next_memory[MAX_VARIABLES],
    bit_t candidate_vector[MAX_VARIABLES]) {
#pragma HLS INLINE off

    for (int variable_index = 0; variable_index < MAX_VARIABLES; ++variable_index) {
#pragma HLS PIPELINE II=1
        candidate_vector[variable_index] = hard_decision(variable_belief[variable_index]);

        llr_t signed_decision = (candidate_vector[variable_index] == 1) ? -1 : 1;
        llr_t soft_trace = variable_belief[variable_index] - signed_decision;

        llr_t carry_component = (current_memory[variable_index] * leg_config.carry_factor) / 255;
        llr_t inject_component = (soft_trace * (255 - leg_config.carry_factor)) / 255;
        next_memory[variable_index] = carry_component + inject_component;
    }
}

/*
 * Syndrome check:
 *  - computes H * x mod 2 and compares it against the input syndrome
 *  - returns the residual score and convergence flag
 */
static void syndrome_check(
    const bit_t h_matrix[MAX_CHECKS][MAX_VARIABLES],
    const bit_t syndrome[MAX_CHECKS],
    const bit_t candidate_vector[MAX_VARIABLES],
    bit_t residual_syndrome[MAX_CHECKS],
    score_t &residual_score,
    bit_t &converged) {
#pragma HLS INLINE off

    residual_score = 0;
    converged = 1;

    for (int check_index = 0; check_index < MAX_CHECKS; ++check_index) {
#pragma HLS PIPELINE II=1
        bit_t parity = 0;
        for (int variable_index = 0; variable_index < MAX_VARIABLES; ++variable_index) {
#pragma HLS UNROLL
            if (h_matrix[check_index][variable_index] == 1) {
                parity ^= candidate_vector[variable_index];
            }
        }

        residual_syndrome[check_index] = parity ^ syndrome[check_index];
        residual_score += residual_syndrome[check_index];
        if (residual_syndrome[check_index] != 0) {
            converged = 0;
        }
    }
}

/*
 * Top-level HLS entry point:
 *  - executes multiple Relay legs sequentially
 *  - carries soft state between legs
 *  - emits a single lane result suitable for FPGA integration
 */
extern "C" void relay_engine_hls(
    const bit_t h_matrix[MAX_CHECKS][MAX_VARIABLES],
    const bit_t syndrome_in[MAX_CHECKS],
    const llr_t prior_llr_in[MAX_VARIABLES],
    const RelayLegConfigHLS leg_configs[MAX_LEGS],
    const ap_uint<4> leg_count,
    bit_t candidate_out[MAX_VARIABLES],
    bit_t *converged_out,
    ap_uint<1> *valid_out,
    leg_index_t *legs_used_out,
    cycle_t *total_iterations_out,
    cycle_t *convergence_cycle_out,
    cycle_t *total_cycles_out,
    score_t *residual_score_out) {
#pragma HLS INTERFACE ap_ctrl_hs port=return
#pragma HLS DATAFLOW

    llr_t relay_memory[MAX_VARIABLES];
    llr_t current_prior[MAX_VARIABLES];
    llr_t variable_belief[MAX_VARIABLES];
    llr_t next_memory[MAX_VARIABLES];
    llr_t var_to_check[MAX_CHECKS][MAX_VARIABLES];
    llr_t check_to_var[MAX_CHECKS][MAX_VARIABLES];
    bit_t candidate_vector[MAX_VARIABLES];
    bit_t residual_syndrome[MAX_CHECKS];

#pragma HLS ARRAY_PARTITION variable=relay_memory complete dim=1
#pragma HLS ARRAY_PARTITION variable=current_prior complete dim=1
#pragma HLS ARRAY_PARTITION variable=variable_belief complete dim=1
#pragma HLS ARRAY_PARTITION variable=next_memory complete dim=1
#pragma HLS ARRAY_PARTITION variable=candidate_vector complete dim=1
#pragma HLS ARRAY_PARTITION variable=residual_syndrome complete dim=1
#pragma HLS ARRAY_PARTITION variable=var_to_check complete dim=2
#pragma HLS ARRAY_PARTITION variable=check_to_var complete dim=2

    for (int variable_index = 0; variable_index < MAX_VARIABLES; ++variable_index) {
#pragma HLS UNROLL
        relay_memory[variable_index] = 0;
        current_prior[variable_index] = prior_llr_in[variable_index];
        variable_belief[variable_index] = prior_llr_in[variable_index];
        next_memory[variable_index] = 0;
        candidate_vector[variable_index] = 0;
        candidate_out[variable_index] = 0;
        for (int check_index = 0; check_index < MAX_CHECKS; ++check_index) {
#pragma HLS UNROLL
            var_to_check[check_index][variable_index] = 0;
            check_to_var[check_index][variable_index] = 0;
        }
    }

    bit_t working_syndrome[MAX_CHECKS];
#pragma HLS ARRAY_PARTITION variable=working_syndrome complete dim=1
    for (int check_index = 0; check_index < MAX_CHECKS; ++check_index) {
#pragma HLS UNROLL
        working_syndrome[check_index] = syndrome_in[check_index];
        residual_syndrome[check_index] = 0;
    }

    bit_t converged = 0;
    score_t residual_score = 0;
    cycle_t total_iterations = 0;
    cycle_t convergence_cycle = 0;
    ap_uint<1> valid = 0;
    leg_index_t legs_used = 0;

    // A small amount of top-level control is kept explicit so the synthesized
    // hardware still mirrors the Relay concept of multiple sequential legs.
    for (ap_uint<4> leg_index = 0; leg_index < leg_count && leg_index < MAX_LEGS; ++leg_index) {
        RelayLegConfigHLS leg_config = leg_configs[leg_index];

        // Each leg begins from the state carried over by the previous leg.
        for (int variable_index = 0; variable_index < MAX_VARIABLES; ++variable_index) {
#pragma HLS UNROLL
            current_prior[variable_index] = prior_llr_in[variable_index] + relay_memory[variable_index];
        }

        converged = 0;
        for (ap_uint<4> cycle_in_leg = 0; cycle_in_leg < leg_config.schedule_length && cycle_in_leg < MAX_CYCLES_PER_LEG; ++cycle_in_leg) {
#pragma HLS PIPELINE II=1
            gamma_t gamma = leg_config.gamma_schedule[cycle_in_leg];

            variable_node_update(
                h_matrix,
                current_prior,
                relay_memory,
                check_to_var,
                gamma,
                variable_belief,
                var_to_check);

            check_node_update(
                h_matrix,
                working_syndrome,
                var_to_check,
                check_to_var);

            syndrome_check(
                h_matrix,
                working_syndrome,
                candidate_vector,
                residual_syndrome,
                residual_score,
                converged);

            relay_memory_update(
                leg_config,
                variable_belief,
                relay_memory,
                next_memory,
                candidate_vector);

            for (int variable_index = 0; variable_index < MAX_VARIABLES; ++variable_index) {
#pragma HLS UNROLL
                relay_memory[variable_index] = next_memory[variable_index];
                current_prior[variable_index] = variable_belief[variable_index];
                candidate_out[variable_index] = candidate_vector[variable_index];
            }

            ++total_iterations;
            ++convergence_cycle;
            if (converged == 1) {
                valid = 1;
                legs_used = leg_index + 1;
                break;
            }
        }

        if (converged == 1) {
            break;
        }

        legs_used = leg_index + 1;
    }

    if (valid == 0 && leg_count > 0) {
        legs_used = (leg_count < MAX_LEGS) ? leg_count : MAX_LEGS;
    }

    *converged_out = converged;
    *valid_out = valid;
    *legs_used_out = legs_used;
    *total_iterations_out = total_iterations;
    *convergence_cycle_out = convergence_cycle;
    *total_cycles_out = total_iterations;
    *residual_score_out = residual_score;
}
