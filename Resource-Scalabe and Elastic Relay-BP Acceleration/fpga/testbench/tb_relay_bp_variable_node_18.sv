`timescale 1ns/1ps
module tb_relay_bp_variable_node_18;
  localparam int D=9; logic [3:0] degree; logic signed [17:0] physical_prior,previous_marginal,mu_in[0:D-1];logic signed[4:0]gamma_q;
  logic signed[17:0]bias,marginal,nu_out[0:D-1],weight_contribution;logic signed[21:0]incoming_sum;logic accumulator_saturated,hard_decision,bias_saturated,marginal_saturated;logic[D-1:0]nu_saturated;
  integer fd,count,failed,rc,k,tmp,p,m,g,exp_bias,exp_sum,exp_accsat,exp_marg,exp_decision,exp_nu[0:D-1],exp_weight;
  relay_bp_variable_node_18 #(.MAX_DEGREE(D)) dut(.*);
  initial begin count=0;failed=0;fd=$fopen("fpga/verification/locked_b18/variable_vectors.txt","r");if(!fd)$fatal(1,"cannot open variable vectors");
    while(!$feof(fd))begin rc=$fscanf(fd,"%d %d %d %d",tmp,p,m,g);degree=tmp;physical_prior=p;previous_marginal=m;gamma_q=g;
      for(k=0;k<D;k=k+1)rc=rc+$fscanf(fd," %d",mu_in[k]);rc=rc+$fscanf(fd," %d %d %d %d %d",exp_bias,exp_sum,exp_accsat,exp_marg,exp_decision);
      for(k=0;k<D;k=k+1)rc=rc+$fscanf(fd," %d",exp_nu[k]);rc=rc+$fscanf(fd," %d\n",exp_weight);
      if(rc>=28)begin #1;count=count+1;
        if($signed(bias)!==exp_bias||$signed(incoming_sum)!==exp_sum||accumulator_saturated!==exp_accsat[0]||$signed(marginal)!==exp_marg||hard_decision!==exp_decision[0]||$signed(weight_contribution)!==exp_weight)begin failed=failed+1;$display("VAR_FAIL vec=%0d scalar",count);end
        for(k=0;k<D;k=k+1)if($signed(nu_out[k])!==exp_nu[k])begin failed=failed+1;$display("VAR_FAIL vec=%0d edge=%0d got=%0d exp=%0d",count,k,$signed(nu_out[k]),exp_nu[k]);end
      end
    end
    $display("VARIABLE_RESULT tested=%0d failed_outputs=%0d",count,failed);if(failed)$fatal(1,"variable mismatches");$finish;
  end
endmodule
