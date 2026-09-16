#include <stdio.h>
#include <limits.h>

int main(void)
{
	long long a;
	printf("请输入整数a：");
	scanf("%lld", &a);
	
	// =========输入阶段限制范围，边界校验=========
	if(a == LLONG_MAX)
	{
		printf("错误：输入的a等于long long最大值，a+1会发生溢出，拒绝本次计算！\n");
		return 1;
	}
	// 只要走到下面，一定满足 a < LLONG_MAX，a+1绝对不会溢出
	long long res = a + 1;
	printf("a = %lld\n", a);
	printf("a+1 = %lld\n", res);
	if(res > a){
		printf("校验通过：a+1 > a 条件成立\n");
	}else{
		printf("校验失败！\n");
	}
	return 0;
}

