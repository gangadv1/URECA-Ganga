`timescale 1ns/1ps
module tb_relay_bp_check_min2_18;
  localparam int D=9;
  logic [3:0] degree; logic syndrome_bit; logic signed [17:0] nu_in[0:D-1],mu_out[0:D-1];
  logic [18:0] min1,min2; logic [3:0] min1_index; logic negative_parity;
  integer fd,count,failed,rc,k,tmp,expected[0:D-1];
  relay_bp_check_min2_18 #(.MAX_DEGREE(D),.INDEX_W(4)) dut(.*);
  initial begin count=0;failed=0;fd=$fopen("fpga/verification/locked_b18/check_vectors.txt","r"); if(!fd)$fatal(1,"cannot open check vectors");
    while(!$feof(fd)) begin
      rc=$fscanf(fd,"%d %d",tmp,syndrome_bit); degree=tmp;
      for(k=0;k<D;k=k+1) rc=rc+$fscanf(fd," %d",nu_in[k]);
      for(k=0;k<D;k=k+1) rc=rc+$fscanf(fd," %d",expected[k]);
      if(rc>=20) begin #1;count=count+1;for(k=0;k<D;k=k+1)if($signed(mu_out[k])!==expected[k])begin failed=failed+1;$display("CHECK_FAIL vec=%0d edge=%0d got=%0d expected=%0d",count,k,$signed(mu_out[k]),expected[k]);end end
    end
    $display("CHECK_RESULT tested=%0d passed=%0d failed_outputs=%0d",count,count-(failed!=0),failed);if(failed)$fatal(1,"check mismatches");$finish;
  end
endmodule
