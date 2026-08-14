`timescale 1ns/1ps
module tb_relay_bp_engine_cancellation_p4;
 parameter integer TARGET=3;
 localparam C=12,V=20,E=76,L=2;
 logic clk=0,rst=1,start=0,cancel_request=0,cfg_we=0;logic[3:0]cfg_kind;logic[31:0]cfg_addr;logic signed[31:0]cfg_data;
 logic gamma_start,gamma_abort,gamma_ready,gamma_valid,gamma_done;logic[1:0]gamma_leg_index;logic[31:0]gamma_variable_count;logic[4:0]gamma_variable_index;logic signed[4:0]gamma_value;
 logic busy,done,failed,candidate_valid,cancel_ack,cancelled,quiescent,saw_gamma_abort;logic[3:0]phase_state;
 integer cp[0:C],ev[0:E-1],vp[0:V],ve[0:E-1],gamma[0:L*V-1],prior[0:V-1],syn[0:C-1];integer gf,sf,q,one,dummy,timeout,ack_cycle,quiet_cycle;
 always #5 clk=~clk;
 always_ff @(posedge clk)if(rst)saw_gamma_abort<=0;else if(gamma_abort)saw_gamma_abort<=1;
 relay_bp_single_engine_memory_p4 #(.C(C),.V(V),.E(E),.L(L),.STALL_PERIOD(7))dut(.clk,.rst,.start,.cancel_request,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,.first_limit(16'd2),.later_limit(16'd3),.first_gamma(5'sd2),
  .gamma_valid,.gamma_variable_index,.gamma_value,.gamma_done,.gamma_seed_valid(1'b0),.gamma_seed(64'd0),.gamma_updated_state(64'd0),.gamma_start,.gamma_abort,.gamma_leg_index,.gamma_variable_count,.gamma_ready,.gamma_seed_load(),.gamma_seed_state(),
  .busy,.done,.converged(),.failed,.candidate_valid,.total_iterations(),.cancel_ack,.cancelled,.quiescent,.phase_state,.relay_legs(),.selected_weight(),.total_cycles(),.iteration_done(),.trace_leg(),.trace_iteration(),.trace_converged(),.trace_weight(),
  .correction_req(1'b0),.correction_word(0),.correction_ready(),.correction_rsp_valid(),.correction_bits(),.correction_mask(),.check_cycles(),.variable_cycles(),.convergence_cycles(),.relay_cycles(),.wait_cycles());
 relay_bp_deterministic_gamma_source #(.V(V),.L(L),.STALL_PERIOD(5))source(.clk,.rst,.start(gamma_start),.abort(gamma_abort),.leg_index(gamma_leg_index),.variable_count(gamma_variable_count),.ready(gamma_ready),.valid(gamma_valid),.variable_index(gamma_variable_index),.value(gamma_value),.done(gamma_done));
 task cfg(input integer k,a,d);begin @(negedge clk);cfg_we=1;cfg_kind=k;cfg_addr=a;cfg_data=d;@(negedge clk);cfg_we=0;end endtask
 initial begin
  gf=$fopen("fpga/verification/memory_backed_engine/graph.txt","r");sf=$fopen("fpga/verification/memory_backed_engine/shots.txt","r");if(!gf||!sf)$fatal(1,"vectors missing");
  for(q=0;q<=C;q=q+1)one=$fscanf(gf,"%d",cp[q]);for(q=0;q<E;q=q+1)one=$fscanf(gf,"%d",ev[q]);for(q=0;q<=V;q=q+1)one=$fscanf(gf,"%d",vp[q]);for(q=0;q<E;q=q+1)one=$fscanf(gf,"%d",ve[q]);for(q=0;q<L*V;q=q+1)one=$fscanf(gf,"%d",gamma[q]);for(q=0;q<L*V;q=q+1)source.fixture[q]=gamma[q];
  one=$fscanf(sf,"%d",dummy);for(q=0;q<V;q=q+1)one=one+$fscanf(sf," %d",prior[q]);for(q=0;q<C;q=q+1)one=one+$fscanf(sf," %d",syn[q]);
  repeat(2)@(posedge clk);rst=0;for(q=0;q<=C;q=q+1)cfg(0,q,cp[q]);for(q=0;q<E;q=q+1)begin cfg(1,q,ev[q]);cfg(3,q,ve[q]);end for(q=0;q<=V;q=q+1)cfg(2,q,vp[q]);for(q=0;q<V;q=q+1)begin cfg(4,q,prior[q]);cfg(10,q,prior[q]);end for(q=0;q<C;q=q+1)cfg(5,q,syn[q]);
  @(negedge clk)start=1;@(negedge clk)start=0;timeout=0;
  if(TARGET==11)begin while(!(phase_state==4&&dut.v_misc2>0)&&timeout<100000)begin @(posedge clk);timeout=timeout+1;end end
  else if(TARGET==12)begin while(!(phase_state==1&&dut.leg_index==1)&&timeout<100000)begin @(posedge clk);timeout=timeout+1;end end
  else if(TARGET==13)begin while(!(phase_state==4&&dut.var_u.state==14&&dut.var_u.selected_mask!=dut.var_u.pending_mask)&&timeout<100000)begin @(posedge clk);timeout=timeout+1;end end
  else if(TARGET==14)begin while(!(phase_state==4&&dut.var_u.state==21&&dut.var_u.selected_mask!=dut.var_u.pending_mask)&&timeout<100000)begin @(posedge clk);timeout=timeout+1;end end
  else while(phase_state!=TARGET&&timeout<100000)begin @(posedge clk);timeout=timeout+1;end
  if(timeout>=100000)$fatal(1,"target phase not reached target=%0d state=%0d",TARGET,phase_state);
  @(negedge clk)cancel_request=1;@(negedge clk)cancel_request=0;ack_cycle=-1;quiet_cycle=-1;timeout=0;
  while(!quiescent&&timeout<100000)begin @(posedge clk);timeout=timeout+1;if(cancel_ack&&ack_cycle<0)ack_cycle=timeout;end
  if(cancel_ack&&ack_cycle<0)ack_cycle=timeout;if(quiescent)quiet_cycle=timeout;
  if(!quiescent||!cancelled||candidate_valid||failed||done)$fatal(1,"unsafe cancellation target=%0d",TARGET);
  repeat(5)begin @(posedge clk);if(busy||candidate_valid||dut.req_valid||dut.rsp_valid)$fatal(1,"post-quiescent activity target=%0d",TARGET);end
  if((TARGET==1||TARGET==12)&&!saw_gamma_abort)$fatal(1,"gamma cancellation lacked abort target=%0d",TARGET);
  $display("CANCEL_PHASE_RESULT target=%0d ack_cycles=%0d quiescent_cycles=%0d gamma_abort_seen=%0d retries=%0d pass=1",TARGET,ack_cycle,quiet_cycle,saw_gamma_abort,dut.v_misc2);$finish;
 end
endmodule
