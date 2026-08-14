`timescale 1ns/1ps
module tb_relay_bp_bias18;
  logic signed [17:0] physical_prior, previous_marginal, bias;
  logic signed [4:0] gamma_q;
  logic saturated;
  integer fd, count, failed, rc, p, m, g, expected;
  relay_bp_bias18 dut(.*);
  initial begin
    count=0; failed=0; fd=$fopen("fpga/verification/locked_b18/bias_vectors.txt","r");
    if (!fd) $fatal(1,"cannot open bias vectors");
    while (!$feof(fd)) begin
      rc=$fscanf(fd,"%d %d %d %d\n",p,m,g,expected);
      if (rc==4) begin physical_prior=p; previous_marginal=m; gamma_q=g; #1; count=count+1;
        if ($signed(bias)!==expected) begin failed=failed+1; $display("BIAS_FAIL %0d got=%0d expected=%0d",count,$signed(bias),expected); end
      end
    end
    $display("BIAS_RESULT tested=%0d passed=%0d failed=%0d",count,count-failed,failed);
    if (failed) $fatal(1,"bias mismatches"); $finish;
  end
endmodule
