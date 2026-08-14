`timescale 1ns/1ps
module tb_relay_bp_single_engine_p4;
  localparam C=3,V=4,E=9,L=2;
  logic clk=0,rst=1,start=0,cfg_we=0;
  logic [2:0] cfg_kind;logic [31:0]cfg_addr;logic signed[31:0]cfg_data;
  logic busy,done,converged,failed,iteration_done;logic[31:0]total_iterations;
  logic[1:0]relay_legs,trace_leg;logic[15:0]trace_iteration;logic signed[31:0]candidate_weight;
  integer check_ptr[0:C],edge_var[0:E-1],var_ptr[0:V],var_edge[0:E-1];
  integer priors[0:2][0:V-1],syndromes[0:2][0:C-1];
  integer exp_mu[0:E-1],exp_marg[0:V-1],exp_nu[0:E-1],exp_dec[0:V-1];
  integer fd,final_fd,rc,rc_one,q,shot,rec_shot,rec_leg,rec_iter,exp_conv,records,failed_count,tmp_shot,tmp_value;
  integer final_dec[0:2][0:V-1],final_weight[0:2],final_iters[0:2],final_legs[0:2],final_conv[0:2];
  always #5 clk=~clk;
  relay_bp_single_engine_p4 #(.CHECKS(C),.VARIABLES(V),.EDGES(E),.LEGS(L),.P(4),.MAX_CHECK_DEGREE(3)) dut(.*);
  task write_cfg(input integer kind,input integer addr,input integer data);
    begin @(negedge clk);cfg_kind=kind;cfg_addr=addr;cfg_data=data;cfg_we=1;@(negedge clk);cfg_we=0;end
  endtask
  task load_shot(input integer s);
    begin for(q=0;q<V;q=q+1)write_cfg(4,q,priors[s][q]);for(q=0;q<C;q=q+1)write_cfg(5,q,syndromes[s][q]);end
  endtask
  task read_record;
    begin
      rc=$fscanf(fd,"%d %d %d",rec_shot,rec_leg,rec_iter);
      for(q=0;q<E;q=q+1)rc=rc+$fscanf(fd," %d",exp_mu[q]);
      for(q=0;q<V;q=q+1)rc=rc+$fscanf(fd," %d",exp_marg[q]);
      for(q=0;q<E;q=q+1)rc=rc+$fscanf(fd," %d",exp_nu[q]);
      for(q=0;q<V;q=q+1)rc=rc+$fscanf(fd," %d",exp_dec[q]);
      rc=rc+$fscanf(fd," %d\n",exp_conv);records=records+1;
    end
  endtask
  initial begin
    check_ptr[0]=0;check_ptr[1]=3;check_ptr[2]=6;check_ptr[3]=9;
    edge_var[0]=0;edge_var[1]=1;edge_var[2]=2;edge_var[3]=1;edge_var[4]=2;edge_var[5]=3;edge_var[6]=0;edge_var[7]=2;edge_var[8]=3;
    var_ptr[0]=0;var_ptr[1]=2;var_ptr[2]=4;var_ptr[3]=7;var_ptr[4]=9;
    var_edge[0]=0;var_edge[1]=6;var_edge[2]=1;var_edge[3]=3;var_edge[4]=2;var_edge[5]=4;var_edge[6]=7;var_edge[7]=5;var_edge[8]=8;
    priors[0][0]=7;priors[0][1]=7;priors[0][2]=7;priors[0][3]=7;syndromes[0][0]=0;syndromes[0][1]=0;syndromes[0][2]=0;
    priors[1][0]=-7;priors[1][1]=-7;priors[1][2]=-7;priors[1][3]=-7;syndromes[1][0]=0;syndromes[1][1]=1;syndromes[1][2]=1;
    priors[2][0]=9;priors[2][1]=-5;priors[2][2]=6;priors[2][3]=8;syndromes[2][0]=1;syndromes[2][1]=0;syndromes[2][2]=1;
    fd=$fopen("fpga/verification/small_graph_b18/iteration_vectors.txt","r");if(!fd)$fatal(1,"vectors missing");records=0;failed_count=0;
    final_fd=$fopen("fpga/verification/small_graph_b18/final_vectors.txt","r");if(!final_fd)$fatal(1,"final vectors missing");
    for(shot=0;shot<3;shot=shot+1)begin
      rc=$fscanf(final_fd,"%d %d %d %d %d",tmp_shot,final_conv[shot],final_iters[shot],final_legs[shot],final_weight[shot]);
      for(q=0;q<V;q=q+1)begin rc_one=$fscanf(final_fd," %d",tmp_value);final_dec[shot][q]=tmp_value;rc=rc+rc_one;end
    end
    repeat(2)@(posedge clk);#1 rst=0;
    for(q=0;q<=C;q=q+1)write_cfg(0,q,check_ptr[q]);for(q=0;q<E;q=q+1)write_cfg(1,q,edge_var[q]);
    for(q=0;q<=V;q=q+1)write_cfg(2,q,var_ptr[q]);for(q=0;q<E;q=q+1)write_cfg(3,q,var_edge[q]);
    for(q=0;q<V;q=q+1)begin write_cfg(6,q,2);write_cfg(6,V+q,(q==0)?-4:(q==1)?2:(q==2)?4:0);end
    write_cfg(7,0,2);write_cfg(7,1,3);read_record();
    for(shot=0;shot<3;shot=shot+1)begin
      load_shot(shot);@(negedge clk);start=1;@(negedge clk);start=0;
      while(!done)begin @(posedge clk);#1;if(iteration_done)begin
        if(rec_shot!=shot||trace_leg!=rec_leg||trace_iteration!=rec_iter)begin failed_count=failed_count+1;$display("TRACE_ID_FAIL shot=%0d",shot);end
        for(q=0;q<E;q=q+1)if($signed(dut.mu_mem[q])!=exp_mu[q])begin failed_count=failed_count+1;$display("MU_FAIL shot=%0d leg=%0d iter=%0d edge=%0d exp=%0d got=%0d",shot,rec_leg,rec_iter,q,exp_mu[q],$signed(dut.mu_mem[q]));end
        for(q=0;q<V;q=q+1)begin if($signed(dut.marginal_mem[q])!=exp_marg[q])begin failed_count=failed_count+1;$display("MARG_FAIL shot=%0d leg=%0d iter=%0d var=%0d exp=%0d got=%0d",shot,rec_leg,rec_iter,q,exp_marg[q],$signed(dut.marginal_mem[q]));end if(dut.decision_mem[q]!=exp_dec[q])begin failed_count=failed_count+1;$display("DEC_FAIL shot=%0d var=%0d",shot,q);end end
        for(q=0;q<E;q=q+1)if($signed(dut.nu_mem[q])!=exp_nu[q])begin failed_count=failed_count+1;$display("NU_FAIL shot=%0d edge=%0d exp=%0d got=%0d",shot,q,exp_nu[q],$signed(dut.nu_mem[q]));end
        if(!$feof(fd))read_record();
      end end
      if(converged!=final_conv[shot]||total_iterations!=final_iters[shot]||relay_legs!=final_legs[shot]||$signed(candidate_weight)!=final_weight[shot])begin failed_count=failed_count+1;$display("FINAL_FAIL shot=%0d conv=%0d it=%0d legs=%0d weight=%0d",shot,converged,total_iterations,relay_legs,$signed(candidate_weight));end
      for(q=0;q<V;q=q+1)if(dut.decision_mem[q]!=final_dec[shot][q])begin failed_count=failed_count+1;$display("CORRECTION_FAIL shot=%0d var=%0d",shot,q);end
    end
    $display("ENGINE_RESULT shots=3 iteration_records=%0d failed=%0d",records,failed_count);if(failed_count)$fatal(1,"complete-engine mismatch");$finish;
  end
endmodule
