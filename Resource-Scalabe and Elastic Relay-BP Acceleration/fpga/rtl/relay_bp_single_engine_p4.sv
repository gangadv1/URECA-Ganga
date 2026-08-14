// Complete S=1 folded Relay-BP trajectory engine for sparse-graph verification.
// Internal arrays model synchronous local memories; graph/shot loading is explicit.
module relay_bp_single_engine_p4 #(
  parameter int CHECKS=3, VARIABLES=4, EDGES=9, LEGS=2, P=4,
  parameter int MAX_CHECK_DEGREE=242, MAX_VARIABLE_DEGREE=9,
  parameter int AW_E=(EDGES<=1)?1:$clog2(EDGES),
  parameter int AW_V=(VARIABLES<=1)?1:$clog2(VARIABLES),
  parameter int AW_C=(CHECKS<=1)?1:$clog2(CHECKS),
  parameter int IW=16, LW=(LEGS<=1)?1:$clog2(LEGS+1)
) (
  input logic clk, rst, start,
  input logic cfg_we, input logic [2:0] cfg_kind, input logic [31:0] cfg_addr,
  input logic signed [31:0] cfg_data,
  output logic busy, done, converged, failed,
  output logic [31:0] total_iterations,
  output logic [LW-1:0] relay_legs,
  output logic signed [31:0] candidate_weight,
  output logic iteration_done,
  output logic [LW-1:0] trace_leg,
  output logic [IW-1:0] trace_iteration
);
  localparam logic signed [17:0] MAX18=18'sd131071, MIN18=-18'sd131072;
  typedef enum logic [4:0] {IDLE,INIT_LEG,CHECK_SETUP,CHECK_PASS1,CHECK_PASS2,
    VAR_SETUP,VAR_BIAS,VAR_ACCUM,VAR_FINISH,VAR_EMIT,CONV_SETUP,CONV_ACCUM,CONV_FINISH,
    ITER_REPORT,NEXT_ITER,NEXT_LEG,DONE_ST,FAIL_ST} state_t;
  state_t state;
  logic [31:0] check_ptr[0:CHECKS], var_ptr[0:VARIABLES];
  logic [AW_V-1:0] edge_var[0:EDGES-1];
  logic [AW_E-1:0] var_edge[0:EDGES-1];
  logic signed [17:0] prior_mem[0:VARIABLES-1], marginal_mem[0:VARIABLES-1];
  logic signed [4:0] gamma_mem[0:LEGS-1][0:VARIABLES-1];
  logic [IW-1:0] iter_limit[0:LEGS-1];
  logic syndrome_mem[0:CHECKS-1], decision_mem[0:VARIABLES-1];
  logic signed [17:0] nu_mem[0:EDGES-1], mu_mem[0:EDGES-1];

  integer q, idx; integer cidx, vidx, chunk, edge_count;
  logic [LW-1:0] leg_index;
  logic [IW-1:0] leg_iteration;
  logic [18:0] c_min1,c_min2,mag,emit_mag;
  integer c_min_index;
  logic c_parity, out_neg;
  logic signed [21:0] v_sum;
  logic signed [17:0] v_bias, v_marginal;
  logic signed [17:0] bias_prior_in, bias_previous_in;
  logic signed [4:0] bias_gamma_in;
  logic v_bias_sat, v_marg_sat;
  logic conv_parity, global_mismatch;
  logic [31:0] residual_weight;
  logic signed [31:0] weight_accum;
  logic signed [18:0] nu_calc;
  logic signed [22:0] sum_calc;

  relay_bp_bias18 bias_u(.physical_prior(bias_prior_in),
    .previous_marginal(bias_previous_in),.gamma_q(bias_gamma_in),
    .bias(v_bias),.saturated(v_bias_sat));

  function automatic signed [17:0] sat18(input signed [22:0] x);
    if(x>23'sd131071) sat18=18'sd131071;
    else if(x< -23'sd131072) sat18=-18'sd131072;
    else sat18=x[17:0];
  endfunction
  function automatic [18:0] abs18(input signed [17:0] x);
    abs18=x[17] ? -$signed({x[17],x}) : {1'b0,x};
  endfunction

  // Configuration write port: 0 check_ptr, 1 edge_var, 2 var_ptr, 3 var_edge,
  // 4 prior, 5 syndrome, 6 gamma (addr=leg*VARIABLES+v), 7 iteration limit.
  always_ff @(posedge clk) if(cfg_we) case(cfg_kind)
    0: check_ptr[cfg_addr] <= cfg_data;
    1: edge_var[cfg_addr] <= cfg_data[AW_V-1:0];
    2: var_ptr[cfg_addr] <= cfg_data;
    3: var_edge[cfg_addr] <= cfg_data[AW_E-1:0];
    4: prior_mem[cfg_addr] <= cfg_data[17:0];
    5: syndrome_mem[cfg_addr] <= cfg_data[0];
    6: gamma_mem[cfg_addr/VARIABLES][cfg_addr%VARIABLES] <= cfg_data[4:0];
    7: iter_limit[cfg_addr] <= cfg_data[IW-1:0];
  endcase

  always_ff @(posedge clk) begin
    if(rst) begin
      state<=IDLE; busy<=0; done<=0; converged<=0; failed<=0; iteration_done<=0;
      total_iterations<=0; relay_legs<=0; candidate_weight<=0;
    end else begin
      done<=0; iteration_done<=0;
      case(state)
        IDLE: if(start) begin busy<=1; converged<=0; failed<=0; total_iterations<=0;
          leg_index<=0; relay_legs<=1; leg_iteration<=0; weight_accum<=0; candidate_weight<=0; state<=INIT_LEG;
          for(q=0;q<VARIABLES;q=q+1) marginal_mem[q]<=prior_mem[q];
        end
        INIT_LEG: begin
          for(q=0;q<EDGES;q=q+1) begin nu_mem[q]<=prior_mem[edge_var[q]]; mu_mem[q]<='0; end
          cidx<=0; state<=CHECK_SETUP;
        end
        CHECK_SETUP: begin c_min1<=19'h3ffff;c_min2<=19'h3ffff;c_min_index<=0;c_parity<=0;chunk<=0;state<=CHECK_PASS1;end
        CHECK_PASS1: begin
          for(q=0;q<P;q=q+1) begin
            idx=check_ptr[cidx]+chunk+q;
            if(idx<check_ptr[cidx+1]) begin
              mag=abs18(nu_mem[idx]); c_parity=c_parity^nu_mem[idx][17];
              if(mag<c_min1) begin c_min2=c_min1;c_min1=mag;c_min_index=chunk+q;end
              else if(mag<c_min2)c_min2=mag;
            end
          end
          if(check_ptr[cidx]+chunk+P>=check_ptr[cidx+1]) begin chunk<=0;state<=CHECK_PASS2;end else chunk<=chunk+P;
        end
        CHECK_PASS2: begin
          edge_count=check_ptr[cidx+1]-check_ptr[cidx];
          for(q=0;q<P;q=q+1) begin idx=check_ptr[cidx]+chunk+q;
            if(idx<check_ptr[cidx+1]) begin
              if(edge_count==1) mu_mem[idx]<=syndrome_mem[cidx] ? -18'sd131071:18'sd131071;
              else begin emit_mag=((chunk+q)==c_min_index)?c_min2:c_min1;
                out_neg=syndrome_mem[cidx]^c_parity^nu_mem[idx][17];
                if(out_neg) mu_mem[idx]<=emit_mag>=131072 ? MIN18 : -$signed(emit_mag[17:0]);
                else mu_mem[idx]<=emit_mag>131071 ? MAX18 : $signed(emit_mag[17:0]);
              end
            end
          end
          if(check_ptr[cidx]+chunk+P>=check_ptr[cidx+1]) begin
            if(cidx==CHECKS-1) begin vidx<=0;state<=VAR_SETUP;end
            else begin cidx<=cidx+1;state<=CHECK_SETUP;end
          end else chunk<=chunk+P;
        end
        VAR_SETUP: begin
          bias_prior_in<=prior_mem[vidx];bias_previous_in<=marginal_mem[vidx];
          bias_gamma_in<=gamma_mem[leg_index][vidx];v_sum<=0;chunk<=0;state<=VAR_BIAS;
        end
        VAR_BIAS: state<=VAR_ACCUM;
        VAR_ACCUM: begin
          sum_calc=$signed(v_sum);
          for(q=0;q<P;q=q+1) begin idx=var_ptr[vidx]+chunk+q;
            if(idx<var_ptr[vidx+1]) sum_calc=sum_calc+$signed(mu_mem[var_edge[idx]]);
          end
          if(sum_calc>2097151)v_sum<=22'sd2097151;else if(sum_calc< -2097152)v_sum<=-22'sd2097152;else v_sum<=sum_calc[21:0];
          if(var_ptr[vidx]+chunk+P>=var_ptr[vidx+1]) state<=VAR_FINISH; else chunk<=chunk+P;
        end
        VAR_FINISH: begin
          sum_calc=$signed(v_bias)+$signed(v_sum); v_marginal=sat18(sum_calc);
          marginal_mem[vidx]<=v_marginal;decision_mem[vidx]<=v_marginal<=0;
          if(v_marginal<=0)weight_accum<=weight_accum+$signed(prior_mem[vidx]);
          chunk<=0;state<=VAR_EMIT;
        end
        VAR_EMIT: begin
          for(q=0;q<P;q=q+1) begin idx=var_ptr[vidx]+chunk+q;
            if(idx<var_ptr[vidx+1]) begin nu_calc=$signed(marginal_mem[vidx])-$signed(mu_mem[var_edge[idx]]);
              nu_mem[var_edge[idx]]<=sat18(nu_calc);
            end
          end
          if(var_ptr[vidx]+chunk+P>=var_ptr[vidx+1]) begin
            if(vidx==VARIABLES-1) begin cidx<=0;global_mismatch<=0;residual_weight<=0;state<=CONV_SETUP;end
            else begin vidx<=vidx+1;state<=VAR_SETUP;end
          end else chunk<=chunk+P;
        end
        CONV_SETUP: begin conv_parity<=0;chunk<=0;state<=CONV_ACCUM;end
        CONV_ACCUM: begin
          for(q=0;q<P;q=q+1) begin idx=check_ptr[cidx]+chunk+q;
            if(idx<check_ptr[cidx+1])conv_parity=conv_parity^decision_mem[edge_var[idx]];
          end
          if(check_ptr[cidx]+chunk+P>=check_ptr[cidx+1])state<=CONV_FINISH;else chunk<=chunk+P;
        end
        CONV_FINISH: begin
          if(conv_parity!=syndrome_mem[cidx])begin global_mismatch<=1;residual_weight<=residual_weight+1;end
          if(cidx==CHECKS-1)state<=ITER_REPORT;else begin cidx<=cidx+1;state<=CONV_SETUP;end
        end
        ITER_REPORT: begin
          total_iterations<=total_iterations+1;leg_iteration<=leg_iteration+1;iteration_done<=1;
          trace_leg<=leg_index+1;trace_iteration<=leg_iteration+1;candidate_weight<=weight_accum;
          if(!global_mismatch)begin converged<=1;state<=DONE_ST;end
          else if(leg_iteration+1>=iter_limit[leg_index])state<=NEXT_LEG;else state<=NEXT_ITER;
        end
        NEXT_ITER: begin weight_accum<=0;cidx<=0;state<=CHECK_SETUP;end
        NEXT_LEG: begin
          if(leg_index+1>=LEGS)state<=FAIL_ST;
          else begin leg_index<=leg_index+1;relay_legs<=relay_legs+1;leg_iteration<=0;weight_accum<=0;state<=INIT_LEG;end
        end
        DONE_ST: begin busy<=0;done<=1;state<=IDLE;end
        FAIL_ST: begin busy<=0;failed<=1;done<=1;state<=IDLE;end
        default:state<=IDLE;
      endcase
    end
  end
endmodule
