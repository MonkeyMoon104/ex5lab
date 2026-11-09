#property copyright "ex5lab examples"
#property version   "1.00"
#property strict

int Scale(const int x)
{
   return (x * 3) + 11;
}

int OnInit()
{
   int y = Scale(7);
   Print("EXAMPLE_ARITH y=", y);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) {}
void OnTick() {}
